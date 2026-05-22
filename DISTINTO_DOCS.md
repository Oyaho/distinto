# DISTINTO — Autenticação Descentralizada de Bolsas de Luxo

> **TCC · Felipe Braga** — Sistema de autenticação de artigos de luxo usando Blockchain (Ethereum/Ganache) + Inteligência Artificial (Vision Transformer no Hugging Face).

---

## Sumário

1. [Visão Geral do Projeto](#1-visão-geral-do-projeto)
2. [Arquitetura](#2-arquitetura)
3. [Estrutura de Arquivos](#3-estrutura-de-arquivos)
4. [Smart Contract — `LuxuryItemRegistry.sol`](#4-smart-contract--luxuryitemregistrysol)
5. [Backend — `main.py`](#5-backend--mainpy)
   - [Inicialização e Deploy do Contrato](#51-inicialização-e-deploy-do-contrato)
   - [POST `/api/register` — Cadastro do Produto](#52-post-apiregister--cadastro-do-produto)
   - [POST `/api/transfer` — Transferência de Dono](#53-post-apitransfer--transferência-de-dono)
   - [GET `/api/verify/{serial_number}` — Verificação Blockchain](#54-get-apiverifyserialnumber--verificação-blockchain)
   - [POST `/api/verify-image/{serial_number}` — Análise de Similaridade com IA](#55-post-apivery-imageserialnumber--análise-de-similaridade-com-ia)
   - [GET `/api/accounts` — Contas Ganache](#56-get-apiaccounts--contas-ganache)
6. [Frontend — `static/index.html`](#6-frontend--staticindexhtml)
7. [Infraestrutura Docker](#7-infraestrutura-docker)
8. [Fluxo Completo de Uso](#8-fluxo-completo-de-uso)
9. [Dependências](#9-dependências)
10. [Variáveis de Ambiente](#10-variáveis-de-ambiente)

---

## 1. Visão Geral do Projeto

**DISTINTO** é um sistema de autenticação de bolsas de luxo que combina **blockchain imutável** com **visão computacional por IA**. O objetivo é criar um "passaporte digital" para cada produto, armazenado em um smart contract Ethereum, que não pode ser adulterado. Quando um comprador precisa verificar se uma bolsa é autêntica, o sistema cruza dois canais independentes:

| Camada | Tecnologia | O que faz |
|--------|-----------|-----------|
| **Determinística** | Ethereum (Ganache) + Solidity | Armazena e recupera metadados imutáveis do produto na blockchain |
| **Estocástica** | Vision Transformer (ViT) no Hugging Face | Classifica a imagem da bolsa e calcula a similaridade com o modelo registrado |

O veredicto final é gerado pelo **cruzamento** dessas duas camadas, tornando muito mais difícil a falsificação de certificados.

---

## 2. Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                      NAVEGADOR DO USUÁRIO                   │
│               static/index.html (Vanilla HTML/JS)           │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP REST
┌────────────────────────▼────────────────────────────────────┐
│                   BACKEND FastAPI (Python)                   │
│                        main.py :8000                        │
│                                                             │
│  /api/register  →  Cadastra produto na blockchain           │
│  /api/transfer  →  Transfere dono do produto                │
│  /api/verify    →  Lê dados do produto na blockchain        │
│  /api/verify-image → IA Local + blockchain = veredicto      │
└───────────┬─────────────────────────────┬───────────────────┘
            │ web3.py (JSON-RPC)          │ Local Inference
┌───────────▼──────────┐      ┌───────────▼───────────────────┐
│  GANACHE :8545       │      │  TRANSFORMERS PIPELINE        │
│  (Ethereum local)    │      │  (Carregado sob demanda na RAM│
│                      │      │   apenas durante o POST)      │
│  LuxuryItemRegistry  │      │  felipeoya/meu-agente-de-     │
│  .sol (compilado na  │      │  bolsas-luxo (ViT)            │
│  inicialização)      │      └───────────────────────────────┘
└──────────────────────┘
```

---

## 3. Estrutura de Arquivos

```
distinto/
├── main.py                  # Backend FastAPI — toda a lógica de negócio
├── requirements.txt         # Dependências Python
├── Dockerfile               # Imagem Docker do backend
├── docker-compose.yml       # Orquestração: Ganache + API
├── contracts/
│   └── LuxuryItemRegistry.sol  # Smart contract Solidity
└── static/
    └── index.html           # Frontend single-page (sem frameworks)
```

---

## 4. Smart Contract — `LuxuryItemRegistry.sol`

**Arquivo:** [`contracts/LuxuryItemRegistry.sol`](contracts/LuxuryItemRegistry.sol)  
**Compilador:** Solidity `^0.8.21`

### Struct `LuxuryItem`

Cada produto registrado é armazenado como uma struct com os seguintes campos:

```solidity
struct LuxuryItem {
    string serialNumber;      // Número de série único do produto
    string productName;       // Nome do produto (ex: "Chanel Classic Flap")
    string productType;       // Tipo (ex: "Bolsa", "Carteira")
    string color;             // Cor do artigo
    string technicalDetails;  // Detalhes técnicos (material, hardware, etc.)
    string qrCodeData;        // Dados embutidos no QR Code do produto
    address currentOwner;     // Endereço Ethereum do dono atual
    uint256 registeredAt;     // Timestamp Unix do momento do cadastro (block.timestamp)
    bool exists;              // Flag de existência (evita entradas zeradas)
}
```

O mapeamento central é:
```solidity
mapping(string => LuxuryItem) private registry;
// chave: serialNumber → valor: LuxuryItem
```

### Eventos emitidos

| Evento | Quando é emitido |
|--------|-----------------|
| `ItemRegistered(serialNumber, owner, timestamp)` | Ao cadastrar um novo produto |
| `OwnershipTransferred(serialNumber, previousOwner, newOwner, timestamp)` | Ao transferir a propriedade |

> Eventos ficam permanentemente no log da blockchain — servem como trilha de auditoria imutável.

### Funções do contrato

#### `registerItem(serial, name, type, color, details, qrCode)`
- Verifica que o serial ainda não está cadastrado (`require(!registry[_serial].exists)`)
- Grava a struct `LuxuryItem` com `msg.sender` como `currentOwner`
- Emite `ItemRegistered`

#### `transferOwnership(serial, newOwner)`
- Verifica que o item existe
- Verifica que `msg.sender` é o dono atual (`require(registry[_serial].currentOwner == msg.sender)`)
- Valida que `newOwner != address(0)`
- Atualiza `currentOwner` e emite `OwnershipTransferred`

#### `checkAuthenticity(serial)` → (found, serialNumber, productName, productType, color, technicalDetails, qrCodeData, currentOwner, registeredAt)
- Função `view` (não gasta gas, apenas leitura)
- Retorna `(false, "", "", ...)` se o item não existir
- Retorna todos os campos da struct se o item for encontrado

---

## 5. Backend — `main.py`

**Arquivo:** [`main.py`](main.py)  
**Framework:** FastAPI + Uvicorn  
**Blockchain:** web3.py conectando ao Ganache via JSON-RPC  

### 5.1 Inicialização e Deploy do Contrato

Na inicialização da aplicação (usando o `lifespan` do FastAPI), a função `deploy_contract()` executa automaticamente:

```
1. Conecta ao Ganache (com retry de até 15 tentativas, 2s de intervalo)
2. Lê o arquivo .sol em contracts/LuxuryItemRegistry.sol
3. Compila o Solidity com py-solc-x (versão 0.8.21, instalada automaticamente)
4. Faz o deploy do contrato na rede local
5. Salva a referência do contrato nas variáveis globais (w3, contract, admin_account)
```

O `admin_account` é sempre `w3.eth.accounts[0]` — a primeira conta do Ganache.

---

### 5.2 `POST /api/register` — Cadastro do Produto

**Modelo de entrada (`RegisterRequest`):**

```json
{
  "serial_number": "LV-MONO-2024-001",
  "product_name": "Louis Vuitton Speedy 30",
  "product_type": "Bolsa",
  "color": "Marrom Monograma",
  "technical_details": "Canvas monograma, alça de couro, ferragens douradas",
  "qr_code_data": "DISTINTO:LV-MONO-2024-001"
}
```

**O que acontece internamente:**

1. Chama `contract.functions.registerItem(...)` com todos os campos
2. A transação é enviada a partir do `admin_account`
3. Aguarda o recibo da transação (mineração pelo Ganache)
4. Retorna `transaction_hash`, `block_number` e `serial_number`

**Resposta de sucesso:**
```json
{
  "success": true,
  "transaction_hash": "0xabc123...",
  "block_number": 7,
  "serial_number": "LV-MONO-2024-001"
}
```

> O QR code é gerado no **frontend** usando a lib `qrcode.js` e o dado `qr_code_data` (que pode ser o próprio serial number ou uma URL de verificação) é armazenado imutavelmente na blockchain junto com o produto.

---

### 5.3 `POST /api/transfer` — Transferência de Dono

**Modelo de entrada (`TransferRequest`):**

```json
{
  "serial_number": "LV-MONO-2024-001",
  "new_owner_address": "0xAbCd1234..."
}
```

**O que acontece internamente:**

1. Chama `checkAuthenticity` para buscar o produto e descobrir o `current_owner`
2. Valida que o `current_owner` é uma conta disponível no Ganache local (limitação da rede de desenvolvimento)
3. Converte o endereço do novo dono para checksum (EIP-55)
4. Chama `contract.functions.transferOwnership(serial, new_owner)` usando o `current_owner` como remetente
5. Aguarda o recibo e retorna os endereços `from` e `to`

**Resposta de sucesso:**
```json
{
  "success": true,
  "transaction_hash": "0xdef456...",
  "block_number": 12,
  "from_address": "0xOldOwner...",
  "to_address": "0xNewOwner..."
}
```

> A transferência de propriedade é a forma de rastrear a **cadeia de custódia** do produto. Cada venda é registrada imutavelmente na blockchain.

---

### 5.4 `GET /api/verify/{serial_number}` — Verificação Blockchain

**Exemplo de chamada:**
```
GET /api/verify/LV-MONO-2024-001
```

**O que acontece internamente:**

1. Chama `contract.functions.checkAuthenticity(serial_number).call()` (leitura pura, sem gas)
2. Se `result[0] == False`, retorna `{"found": false}`
3. Se encontrado, mapeia cada campo do tuple retornado para um JSON legível

**Resposta quando encontrado:**
```json
{
  "found": true,
  "serial_number": "LV-MONO-2024-001",
  "product_name": "Louis Vuitton Speedy 30",
  "product_type": "Bolsa",
  "color": "Marrom Monograma",
  "technical_details": "Canvas monograma, alça de couro, ferragens douradas",
  "qr_code_data": "DISTINTO:LV-MONO-2024-001",
  "current_owner": "0xAdmin...",
  "registered_at": 1716123456
}
```

O mapeamento do tuple do Solidity para o Python é:

| Índice | Campo |
|--------|-------|
| `result[0]` | `found` (bool) |
| `result[1]` | `serial_number` |
| `result[2]` | `product_name` |
| `result[3]` | `product_type` |
| `result[4]` | `color` |
| `result[5]` | `technical_details` |
| `result[6]` | `qr_code_data` |
| `result[7]` | `current_owner` (address) |
| `result[8]` | `registered_at` (timestamp) |

---

### 5.5 `POST /api/verify-image/{serial_number}` — Análise de Similaridade com IA

Este é o endpoint mais complexo do sistema. Ele implementa **autenticação de dupla camada**.

**Entrada:** `multipart/form-data` com campo `file` (imagem da bolsa)

**Fluxo interno — 4 etapas:**

```
ETAPA 1: Leitura dos bytes da imagem (UploadFile)
    ↓
ETAPA 2: Inferência Local com Modelo ViT (Hugging Face / Transformers)
    O modelo é baixado no primeiro acesso e fica cacheado no container.
    A inferência ocorre com Lazy Loading: a IA é alocada na RAM
    apenas por alguns segundos e logo limpa (gc.collect()).
    Retorno: [{"label": "Louis Vuitton Speedy 30", "score": 0.94}, ...]
    ↓
ETAPA 3: Consulta à blockchain pelo serial_number
    checkAuthenticity(serial_number) → dados imutáveis do produto
    ↓
ETAPA 4: Cross-validation e veredicto
```

#### Lógica do Veredicto

```python
# Normalização: lowercase + colapso de espaços
norm_detected = normalize(detected_model_from_AI)
norm_chain    = normalize(product_name_from_blockchain)
names_match   = norm_detected in norm_chain OR norm_chain in norm_detected

# Decisão:
if not chain_found:
    → "Não Registrada (Serial não encontrado na blockchain)"  [not_found]

elif names_match AND proximity_pct > 80%:
    → "Autêntica"  [authentic]

elif names_match AND proximity_pct <= 80%:
    → "Suspeita (Possível Réplica / Alta Similaridade)"  [suspect]

else:  # nomes divergem
    → "Divergente (ID clonado ou etiqueta adulterada)"  [divergent]
```

#### Casos tratados especialmente

| Situação | Código HTTP | Comportamento |
|----------|------------|---------------|
| Modelo IA ainda carregando | — | Retorna `{"status": "loading"}` com mensagem em PT-BR |
| Timeout (>30s) | 504 | Mensagem de erro amigável |
| Erro HTTP no HF | 502 | Repassa o erro da API de visão |

**Resposta completa:**
```json
{
  "status": "ok",
  "serial_number": "LV-MONO-2024-001",
  "ai": {
    "detected_model": "Louis Vuitton Speedy 30",
    "proximity_pct": 94.21
  },
  "blockchain": {
    "found": true,
    "product_name": "Louis Vuitton Speedy 30",
    "product_type": "Bolsa",
    "color": "Marrom Monograma",
    "current_owner": "0xAdmin...",
    "registered_at": 1716123456
  },
  "veredict": "Autêntica",
  "veredict_code": "authentic"
}
```

---

### 5.6 `GET /api/accounts` — Contas Ganache

Retorna todas as contas disponíveis na rede local com seus saldos em ETH. Útil no frontend para popular o seletor de novo dono na transferência.

```json
{
  "accounts": ["0xAcc1...", "0xAcc2...", ...],
  "balances": {"0xAcc1...": "100", ...},
  "admin": "0xAcc1..."
}
```

---

## 6. Frontend — `static/index.html`

**Arquivo:** [`static/index.html`](static/index.html)  
**Tecnologia:** HTML + CSS (Vanilla) + JavaScript puro  
**Design:** Dark mode luxuoso com paleta ouro/preto, fonte *Playfair Display* + *Inter*, glassmorphism, micro-animações

### Abas da interface

| Aba | Função |
|-----|--------|
| **Dashboard** | Cadastro do produto + geração do QR Code |
| **Transferência** | Formulário para trocar o dono do produto |
| **Verificação** | Busca por serial number + upload de imagem para análise IA |

### Fluxo do QR Code (Dashboard)

1. Usuário preenche todos os campos do produto
2. Clica em "Registrar na Blockchain"
3. O frontend chama `POST /api/register`
4. Com sucesso, a lib **QRCode.js** (CDN) gera o QR Code dinamicamente a partir do `qr_code_data`
5. O QR Code é exibido para download/impressão e colagem física no produto

### Paleta de cores

```css
--gold:    #D4AF37  /* cor primária — dourado clássico */
--bronze:  #cd7f32  /* dropzone e acentos */
--emerald: #2ecc71  /* resultado "Autêntica" */
--amber:   #f39c12  /* resultado "Suspeita" */
--crimson: #e74c3c  /* resultado "Divergente" / erros */
```

### "Passaporte Digital" de Verificação

Quando a verificação retorna um resultado, o frontend renderiza um card chamado **Passport** que exibe:
- Badge de veredicto colorido (🟢 Autêntico / 🟡 Suspeito / 🔴 Divergente)
- Painel da IA: modelo detectado + porcentagem de similaridade
- Painel da blockchain: dados imutáveis do produto + dono atual

---

## 7. Infraestrutura Docker

**Arquivo:** [`docker-compose.yml`](docker-compose.yml)

Dois serviços sobem juntos:

```yaml
ganache:                         # Blockchain Ethereum local
  image: trufflesuite/ganache
  ports: ["8545:8545"]
  command: >
    --accounts 10                # 10 contas pré-financiadas
    --defaultBalanceEther 100    # 100 ETH cada
    --deterministic              # mesmas chaves toda vez que sobe
    --host 0.0.0.0

api:                             # Backend FastAPI
  build: .                       # usa o Dockerfile local
  ports: ["8000:8000"]
  depends_on: [ganache]
  environment:
    - GANACHE_URL=http://ganache:8545
    - HF_TOKEN=${HF_TOKEN}       # token do Hugging Face via .env
```

**Dockerfile** (backend):
```
python:3.12-slim
  → instala gcc (para compilar extensões nativas)
  → pip install -r requirements.txt
  → pre-instala solc 0.8.21 (evita download em runtime)
  → uvicorn main:app --host 0.0.0.0 --port 8000
```

> O `--deterministic` no Ganache garante que os endereços das contas são sempre os mesmos (derivados do mesmo seed BIP39), permitindo que o `admin_account` seja consistente entre reinicializações de desenvolvimento.

---

## 8. Fluxo Completo de Uso

```
FABRICANTE / LOJA
─────────────────
1. Acessa a aba "Dashboard"
2. Preenche: serial, nome, tipo, cor, detalhes técnicos, dado do QR
3. Clica "Registrar na Blockchain"
   → POST /api/register → smart contract grava imutavelmente
4. QR Code é gerado e impresso → colado fisicamente na bolsa

VENDA (TRANSFERÊNCIA DE DONO)
──────────────────────────────
5. Acessa aba "Transferência"
6. Informa o serial + endereço Ethereum do comprador
7. Clica "Transferir Propriedade"
   → POST /api/transfer → contrato muda currentOwner

COMPRADOR / VERIFICADOR
────────────────────────
8. Escaneia o QR Code da bolsa → obtém o serial number
9. Acessa aba "Verificação"
10a. Busca apenas pelo serial:
    → GET /api/verify/{serial} → retorna dados imutáveis da blockchain

10b. (Opcional) Faz upload de uma foto da bolsa:
    → POST /api/verify-image/{serial}
    → IA classifica a imagem (modelo ViT fine-tunado em bolsas de luxo)
    → Sistema cruza o modelo detectado com o nome registrado na blockchain
    → Exibe o "Passaporte Digital" com veredicto: Autêntica / Suspeita / Divergente
```

---

## 9. Dependências

**`requirements.txt`:**

| Pacote | Função |
|--------|--------|
| `fastapi` | Framework web REST |
| `uvicorn[standard]` | Servidor ASGI (suporte a async/websockets) |
| `web3` | Comunicação com o nó Ethereum via JSON-RPC |
| `py-solc-x` | Compilação do Solidity em Python |
| `pydantic` | Validação dos modelos de request/response |
| `httpx` | Utilizado para eventuais requisições (mantido para compatibilidade) |
| `python-multipart` | Suporte a upload de arquivos (`multipart/form-data`) |
| `transformers` | Inferência local do modelo ViT (Machine Learning) |
| `torch` | PyTorch CPU-only (Motor base do transformers) |
| `Pillow` | Processamento de imagens (recorte, resize, etc) |

**Frontend (via CDN):**
- Google Fonts (Playfair Display, Inter)
- QRCode.js (geração de QR codes no browser)

---

## 10. Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `GANACHE_URL` | `http://localhost:8545` | URL do nó Ethereum (Ganache) |
| `HF_TOKEN` | `""` | Token de autenticação da API Hugging Face |

Para rodar localmente com o token:
```bash
# Crie um arquivo .env na raiz do projeto
HF_TOKEN=hf_seu_token_aqui

# Suba os serviços
docker-compose up --build
```

Acesse: **http://localhost:8000**

---

## Modelo de IA

**Modelo:** `felipeoya/meu-agente-de-bolsas-luxo`  
**Base:** Google ViT (Vision Transformer) fine-tunado em bolsas de luxo  
**Hospedagem:** Localmente no backend (usando pipeline `transformers`)  
**Entrada:** Imagem em bytes (`application/octet-stream`)  
**Estratégia de Memória:** Lazy loading com coleta de lixo imediata (`del pipe; gc.collect()`) para não sobrecarregar máquinas com apenas 4GB de RAM.  
**Saída:** Lista de classificações `[{"label": "...", "score": 0.xx}, ...]`

O modelo foi treinado/fine-tunado especificamente para reconhecer modelos de bolsas de luxo (Louis Vuitton, Chanel, Hermès, etc.), retornando o nome do modelo detectado e a pontuação de confiança. Essa pontuação se torna a **"porcentagem de similaridade"** exibida no Passaporte Digital.

---

*Documentação gerada automaticamente com base na análise do código-fonte. Última atualização: 2026-05-22.*
