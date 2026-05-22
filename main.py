"""
DISTINTO — Decentralized Luxury Handbag Authentication API

FastAPI backend that deploys a Solidity smart contract to a local Ganache
blockchain and exposes REST endpoints for product registration, ownership
transfer, and authenticity verification.
"""

import os
import re
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from web3 import Web3
from solcx import compile_standard, install_solc


# ---------------------------------------------------------------------------
# Hugging Face Vision Transformer Configuration
# ---------------------------------------------------------------------------
# Devido a limitações da rede corporativa e ao endpoint Serverless da HF
# estar desativado para este modelo, a inferência roda localmente.
# O modelo será carregado na memória *sob demanda* (lazy load) para
# economizar RAM na máquina do host.

HF_MODEL_ID = "felipeoya/meu-agente-de-bolsas-luxo"
HF_TOKEN    = os.getenv("HF_TOKEN", "")


# ---------------------------------------------------------------------------
# Request / Response Models
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    serial_number: str
    product_name: str
    product_type: str
    color: str
    technical_details: str
    qr_code_data: str


class TransferRequest(BaseModel):
    serial_number: str
    new_owner_address: str


# ---------------------------------------------------------------------------
# Globals (set once during startup)
# ---------------------------------------------------------------------------

w3: Web3 = None          # type: ignore[assignment]
contract = None
admin_account: str = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Contract Compilation & Deployment
# ---------------------------------------------------------------------------

def deploy_contract() -> None:
    """Compile the Solidity contract and deploy it to the Ganache blockchain."""
    global w3, contract, admin_account

    ganache_url = os.getenv("GANACHE_URL", "http://localhost:8545")

    # ---- Connect to Ganache (retry for Docker startup ordering) ----------
    max_retries = 15
    for attempt in range(1, max_retries + 1):
        w3 = Web3(Web3.HTTPProvider(ganache_url))
        if w3.is_connected():
            break
        print(f"[DISTINTO] Waiting for Ganache ({attempt}/{max_retries})...")
        time.sleep(2)
    else:
        raise RuntimeError(f"Cannot connect to Ganache at {ganache_url}")

    admin_account = w3.eth.accounts[0]

    # ---- Read Solidity source -------------------------------------------
    contract_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "contracts",
        "LuxuryItemRegistry.sol",
    )
    with open(contract_path, "r", encoding="utf-8") as fh:
        source_code = fh.read()

    # ---- Compile ---------------------------------------------------------
    print("[DISTINTO] Compiling smart contract...")
    install_solc("0.8.21")
    compiled = compile_standard(
        {
            "language": "Solidity",
            "sources": {
                "LuxuryItemRegistry.sol": {"content": source_code},
            },
            "settings": {
                "outputSelection": {
                    "*": {"*": ["abi", "evm.bytecode"]},
                },
            },
        },
        solc_version="0.8.21",
    )

    contract_data = compiled["contracts"]["LuxuryItemRegistry.sol"][
        "LuxuryItemRegistry"
    ]
    abi = contract_data["abi"]
    bytecode = contract_data["evm"]["bytecode"]["object"]

    # ---- Deploy ----------------------------------------------------------
    print("[DISTINTO] Deploying contract to Ganache...")
    ContractClass = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = ContractClass.constructor().transact({"from": admin_account})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

    contract = w3.eth.contract(
        address=tx_receipt.contractAddress, abi=abi
    )

    print(f"[DISTINTO] ✓ Contract deployed at: {tx_receipt.contractAddress}")
    print(f"[DISTINTO] ✓ Admin account:        {admin_account}")


# ---------------------------------------------------------------------------
# Application Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    deploy_contract()
    yield


app = FastAPI(
    title="DISTINTO API",
    description="Decentralized Luxury Handbag Authentication",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.post("/api/register")
async def register_item(req: RegisterRequest):
    """Register a new luxury item on the blockchain."""
    try:
        tx_hash = contract.functions.registerItem(
            req.serial_number,
            req.product_name,
            req.product_type,
            req.color,
            req.technical_details,
            req.qr_code_data,
        ).transact({"from": admin_account})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        print(
            f"[REGISTER] ✓ Serial: {req.serial_number} "
            f"| TX: {receipt.transactionHash.hex()} "
            f"| Block: {receipt.blockNumber}"
        )

        return {
            "success": True,
            "transaction_hash": receipt.transactionHash.hex(),
            "block_number": receipt.blockNumber,
            "serial_number": req.serial_number,
        }
    except Exception as exc:
        error_msg = str(exc)
        print(f"[REGISTER ERROR] {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)


@app.post("/api/transfer")
async def transfer_ownership(req: TransferRequest):
    """Transfer ownership of a registered item to a new wallet address."""
    try:
        # Look up the item to find the current owner
        result = contract.functions.checkAuthenticity(
            req.serial_number
        ).call()

        if not result[0]:
            raise HTTPException(
                status_code=404,
                detail="Item not found on blockchain",
            )

        current_owner = result[7]  # address field

        # Verify that the current owner is a local Ganache account
        if current_owner not in w3.eth.accounts:
            raise HTTPException(
                status_code=403,
                detail="Current owner account not available in local wallet",
            )

        new_owner = Web3.to_checksum_address(req.new_owner_address)

        tx_hash = contract.functions.transferOwnership(
            req.serial_number, new_owner
        ).transact({"from": current_owner})

        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)

        print(
            f"[TRANSFER] ✓ Serial: {req.serial_number} "
            f"| {current_owner} → {new_owner}"
        )

        return {
            "success": True,
            "transaction_hash": receipt.transactionHash.hex(),
            "block_number": receipt.blockNumber,
            "from_address": current_owner,
            "to_address": new_owner,
        }
    except HTTPException:
        raise
    except Exception as exc:
        error_msg = str(exc)
        print(f"[TRANSFER ERROR] {error_msg}")
        raise HTTPException(status_code=400, detail=error_msg)


@app.get("/api/verify/{serial_number}")
async def verify_item(serial_number: str):
    """Check the authenticity of an item by its serial number."""
    try:
        result = contract.functions.checkAuthenticity(serial_number).call()

        if not result[0]:
            print(f"[VERIFY] ✗ Serial '{serial_number}' NOT FOUND")
            return {"found": False, "serial_number": serial_number}

        print(f"[VERIFY] ✓ Serial '{serial_number}' FOUND — Owner: {result[7]}")

        return {
            "found": True,
            "serial_number": result[1],
            "product_name": result[2],
            "product_type": result[3],
            "color": result[4],
            "technical_details": result[5],
            "qr_code_data": result[6],
            "current_owner": result[7],
            "registered_at": result[8],
        }
    except Exception as exc:
        print(f"[VERIFY ERROR] {str(exc)}")
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/api/verify-image/{serial_number}")
async def verify_image(serial_number: str, file: UploadFile = File(...)):
    """
    Dual-layer authentication:
      1. Stochastic layer  — Google ViT classifies the uploaded image locally.
      2. Deterministic layer — Smart contract returns immutable on-chain metadata.
    The two results are cross-validated to produce a final veredict.
    """
    print(f"[VERIFY-IMAGE] ► serial='{serial_number}'  filename='{file.filename}'")

    # ── Step 1: Read image bytes ──────────────────────────────────────────────
    image_bytes = await file.read()
    print(f"[VERIFY-IMAGE] Image size: {len(image_bytes)} bytes")

    # ── Step 2: Local ViT Inference (Lazy Load) ───────────────────────────────
    # The model is loaded on-demand to save RAM on low-spec machines.
    # After inference, memory is freed immediately via gc.collect().
    vit_result = None
    try:
        print(f"[VERIFY-IMAGE] → Loading Hugging Face ViT model locally into RAM (lazy load)...")
        import gc
        import io
        from PIL import Image
        from transformers import pipeline

        img = Image.open(io.BytesIO(image_bytes))

        # Initialize the pipeline (downloading weights if first time)
        pipe = pipeline(
            "image-classification",
            model=HF_MODEL_ID,
            token=HF_TOKEN,
            device=-1  # Force CPU
        )

        print("[VERIFY-IMAGE] → Running inference on image...")
        predictions = pipe(img)

        # Free memory immediately to protect 4GB RAM machines
        del pipe
        del img
        gc.collect()

        print(f"[VERIFY-IMAGE] ← Local raw predictions: {predictions}")

        # Parse top prediction
        if isinstance(predictions, list) and len(predictions) > 0:
            top = predictions[0]
            detected_model   = top.get("label", "Desconhecido")
            raw_score        = float(top.get("score", 0.0))
            proximity_pct    = round(raw_score * 100, 2)
        else:
            detected_model  = "Desconhecido"
            proximity_pct   = 0.0

        print(f"[VERIFY-IMAGE] ViT → detected_model='{detected_model}'  proximity={proximity_pct}%")
        vit_result = {"detected_model": detected_model, "proximity_pct": proximity_pct}

    except Exception as exc:
        print(f"[VERIFY-IMAGE] ✕ Unexpected ViT error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    # ── Step 3: Read Smart Contract ───────────────────────────────────────────
    print(f"[VERIFY-IMAGE] → Querying blockchain for serial='{serial_number}'…")
    try:
        chain_result = contract.functions.checkAuthenticity(serial_number).call()
    except Exception as exc:
        print(f"[VERIFY-IMAGE] ✕ Blockchain query failed: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))

    chain_found   = chain_result[0]
    chain_name    = chain_result[2] if chain_found else None
    chain_owner   = chain_result[7] if chain_found else None
    chain_ts      = chain_result[8] if chain_found else None
    print(f"[VERIFY-IMAGE] Blockchain → found={chain_found}  product_name='{chain_name}'")

    # ── Step 4: Cross-validate & compute veredict ─────────────────────────────
    def _normalize(s: str) -> str:
        """Lowercase + replace punctuation + collapse whitespace.

        ViT labels often use snake_case (e.g. 'chanel_255') while
        the blockchain stores human-readable names ('Chanel 2.55').
        Removing dots and separators ensures correct matching.
        """
        s = s.strip().lower()
        # Remove dots so '2.55' becomes '255', replace underscores/hyphens with spaces
        s = s.replace(".", "").replace("_", " ").replace("-", " ")
        return re.sub(r"\s+", " ", s)

    if not chain_found:
        # Item not registered on-chain at all
        veredict = "Não Registrada (Serial não encontrado na blockchain)"
        veredict_code = "not_found"
    else:
        # Check if ViT-detected model name overlaps with the on-chain product name
        norm_detected = _normalize(detected_model)
        norm_chain    = _normalize(chain_name)
        names_match   = (
            norm_detected in norm_chain
            or norm_chain in norm_detected
        )

        if names_match and proximity_pct > 80.0:
            veredict = "Autêntica"
            veredict_code = "authentic"
        elif names_match and proximity_pct <= 80.0:
            veredict = "Suspeita (Possível Réplica / Alta Similaridade)"
            veredict_code = "suspect"
        else:
            veredict = "Divergente (ID clonado ou etiqueta adulterada)"
            veredict_code = "divergent"

    print(f"[VERIFY-IMAGE] ✓ VEREDICT: '{veredict}'  (code={veredict_code})")

    return {
        "status": "ok",
        "serial_number": serial_number,
        # AI layer
        "ai": {
            "detected_model":  vit_result["detected_model"],
            "proximity_pct":   vit_result["proximity_pct"],
        },
        # Blockchain layer
        "blockchain": {
            "found":         chain_found,
            "product_name":  chain_name,
            "product_type":  chain_result[3] if chain_found else None,
            "color":         chain_result[4] if chain_found else None,
            "current_owner": chain_owner,
            "registered_at": chain_ts,
        },
        # Final verdict
        "veredict":      veredict,
        "veredict_code": veredict_code,
    }


@app.get("/api/accounts")
async def get_accounts():
    """Return the list of available Ganache accounts and their balances."""
    accounts = w3.eth.accounts
    balances = {}
    for acc in accounts:
        bal = w3.eth.get_balance(acc)
        balances[acc] = str(w3.from_wei(bal, "ether"))

    return {
        "accounts": accounts,
        "balances": balances,
        "admin": admin_account,
    }


# ---------------------------------------------------------------------------
# Static Frontend
# ---------------------------------------------------------------------------

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the main frontend HTML page."""
    return FileResponse(os.path.join(static_dir, "index.html"))
