// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title FaceMatchRegistry
/// @notice Tamper-evident registry of face-identification results.
///         Each record anchors a SHA-256 fingerprint of an evidence bundle
///         (query face embedding + discovered social-media post + metadata)
///         so that anyone can later re-hash the bundle and prove it is
///         unchanged since the moment it was anchored.
contract FaceMatchRegistry {
    struct Record {
        bytes32 recordHash;     // sha256(canonical evidence JSON)
        bytes32 imageHash;      // sha256(bytes of the matched post image)
        bytes32 faceHash;       // sha256(query face embedding vector)
        string postUrl;         // URL of the discovered social-media post
        string platform;        // e.g. "instagram", "x", "facebook"
        uint16 similarityBps;   // cosine similarity * 10000
        uint64 timestamp;       // block timestamp when anchored
        address submitter;      // who anchored it
    }

    mapping(bytes32 => Record) private _records;
    bytes32[] private _hashes;

    event RecordAnchored(
        bytes32 indexed recordHash,
        bytes32 indexed imageHash,
        bytes32 faceHash,
        string postUrl,
        string platform,
        uint16 similarityBps,
        address indexed submitter,
        uint256 timestamp
    );

    error EmptyHash();
    error AlreadyAnchored(bytes32 recordHash);

    /// @notice Anchor a new face-match record. Reverts if the hash is already known.
    function anchor(
        bytes32 recordHash,
        bytes32 imageHash,
        bytes32 faceHash,
        string calldata postUrl,
        string calldata platform,
        uint16 similarityBps
    ) external {
        if (recordHash == bytes32(0)) revert EmptyHash();
        if (_records[recordHash].timestamp != 0) revert AlreadyAnchored(recordHash);

        _records[recordHash] = Record({
            recordHash: recordHash,
            imageHash: imageHash,
            faceHash: faceHash,
            postUrl: postUrl,
            platform: platform,
            similarityBps: similarityBps,
            timestamp: uint64(block.timestamp),
            submitter: msg.sender
        });
        _hashes.push(recordHash);

        emit RecordAnchored(
            recordHash, imageHash, faceHash, postUrl, platform, similarityBps, msg.sender, block.timestamp
        );
    }

    /// @notice True if a record with this hash has been anchored.
    function exists(bytes32 recordHash) external view returns (bool) {
        return _records[recordHash].timestamp != 0;
    }

    /// @notice Fetch a full record. Reverts-free: returns zeroed struct if unknown.
    function getRecord(bytes32 recordHash) external view returns (Record memory) {
        return _records[recordHash];
    }

    /// @notice Number of records anchored so far.
    function count() external view returns (uint256) {
        return _hashes.length;
    }

    /// @notice Record hash at a given index (for enumeration).
    function hashAt(uint256 index) external view returns (bytes32) {
        return _hashes[index];
    }
}
