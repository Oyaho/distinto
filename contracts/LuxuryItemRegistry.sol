// SPDX-License-Identifier: MIT
pragma solidity ^0.8.21;

/// @title LuxuryItemRegistry
/// @notice On-chain registry for luxury handbag authentication and provenance tracking.
contract LuxuryItemRegistry {

    struct LuxuryItem {
        string serialNumber;
        string productName;
        string productType;
        string color;
        string technicalDetails;
        string qrCodeData;
        address currentOwner;
        uint256 registeredAt;
        bool exists;
    }

    mapping(string => LuxuryItem) private registry;

    event ItemRegistered(
        string serialNumber,
        address indexed owner,
        uint256 timestamp
    );

    event OwnershipTransferred(
        string serialNumber,
        address indexed previousOwner,
        address indexed newOwner,
        uint256 timestamp
    );

    /// @notice Register a new luxury item on the blockchain.
    /// @dev Reverts if the serial number is already registered.
    function registerItem(
        string memory _serial,
        string memory _name,
        string memory _type,
        string memory _color,
        string memory _details,
        string memory _qrCode
    ) public {
        require(!registry[_serial].exists, "Item already registered");

        registry[_serial] = LuxuryItem({
            serialNumber: _serial,
            productName: _name,
            productType: _type,
            color: _color,
            technicalDetails: _details,
            qrCodeData: _qrCode,
            currentOwner: msg.sender,
            registeredAt: block.timestamp,
            exists: true
        });

        emit ItemRegistered(_serial, msg.sender, block.timestamp);
    }

    /// @notice Transfer ownership of a registered item.
    /// @dev Only the current owner can call this function.
    function transferOwnership(
        string memory _serial,
        address _newOwner
    ) public {
        require(registry[_serial].exists, "Item not found");
        require(
            registry[_serial].currentOwner == msg.sender,
            "Not the current owner"
        );
        require(_newOwner != address(0), "Invalid new owner address");

        address previousOwner = registry[_serial].currentOwner;
        registry[_serial].currentOwner = _newOwner;

        emit OwnershipTransferred(
            _serial,
            previousOwner,
            _newOwner,
            block.timestamp
        );
    }

    /// @notice Check the authenticity of an item by serial number.
    /// @return found Whether the item exists in the registry.
    function checkAuthenticity(
        string memory _serial
    )
        public
        view
        returns (
            bool found,
            string memory serialNumber,
            string memory productName,
            string memory productType,
            string memory color,
            string memory technicalDetails,
            string memory qrCodeData,
            address currentOwner,
            uint256 registeredAt
        )
    {
        LuxuryItem memory item = registry[_serial];

        if (!item.exists) {
            return (false, "", "", "", "", "", "", address(0), 0);
        }

        return (
            true,
            item.serialNumber,
            item.productName,
            item.productType,
            item.color,
            item.technicalDetails,
            item.qrCodeData,
            item.currentOwner,
            item.registeredAt
        );
    }
}
