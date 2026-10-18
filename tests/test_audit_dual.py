import sys
import os
import unittest
import json

# =========================================================================
# MOCK GENLAYER ENVIRONMENT SUPPORTING CROSS-CONTRACT CALLS (.view & .emit)
# =========================================================================

class MockWebResponse:
    def __init__(self, body_text: str):
        self.body = body_text.encode("utf-8")

class u256(int):
    def __new__(cls, val):
        return super().__new__(cls, int(val))

class Address(str):
    def __new__(cls, val):
        return super().__new__(cls, str(val))

class TreeMap(dict):
    def __getitem__(self, key):
        if key not in self:
            return False
        return super().__getitem__(key)

# Global deployed contracts registry for mock cross-contract dispatch
DEPLOYED_CONTRACTS_MOCK = {}

class MockContractRef:
    def __init__(self, target_instance):
        self.target = target_instance

    def view(self):
        return self.target

    def emit(self, on="finalized"):
        # Synchronously execute for local unit test verification
        return self.target

class MockGL:
    def __init__(self):
        self.message = self.Message()
        self.public = self.Public()
        self.eq_principle = self.EqPrinciple()
        self.nondet = self.NonDet()

        class ContractBase:
            def __new__(cls, *args, **kwargs):
                obj = super().__new__(cls)
                for base in reversed(cls.__mro__):
                    for attr_name, attr_type in getattr(base, "__annotations__", {}).items():
                        type_str = str(attr_type)
                        if "TreeMap" in type_str:
                            setattr(obj, attr_name, TreeMap())
                        elif "u256" in type_str:
                            setattr(obj, attr_name, u256(0))
                        elif "Address" in type_str:
                            setattr(obj, attr_name, Address("0x0000000000000000000000000000000000000000"))
                return obj

        self.Contract = ContractBase

    class Message:
        def __init__(self):
            self.sender_address = Address("0x1111111111111111111111111111111111111111")

    class Public:
        def view(self, func):
            return func
        def write(self, func):
            return func

    class EqPrinciple:
        def __init__(self):
            self.mock_decision = "VERIFIED_ACCURATE"
            self.mock_quote = "totalSupply = 1_000_000 * 10**18;"
            self.mock_rationale = "Code matches declared claims."

        def prompt_non_comparative(self, get_input, task, criteria):
            input_text = get_input()
            if "[EMPTY_SOURCE_CODE_ERROR]" in input_text or "[SOURCE_FETCH_ERROR]" in input_text:
                return json.dumps({
                    "decision": "DECEPTIVE_DISCLOSURE",
                    "verbatim_quote": "NONE",
                    "rationale": "Source code cannot be verified."
                })
            
            # If the code contains the hidden mint function
            if "function mint(address to, uint256 amount) public onlyOwner" in input_text:
                return json.dumps({
                    "decision": "DECEPTIVE_DISCLOSURE",
                    "verbatim_quote": "function mint(address to, uint256 amount) public onlyOwner",
                    "rationale": "Code contains unannounced owner mint function contradicting fixed supply claim."
                })

            return json.dumps({
                "decision": self.mock_decision,
                "verbatim_quote": self.mock_quote,
                "rationale": self.mock_rationale
            })

    class NonDet:
        def __init__(self):
            self.web = self.Web()

        class Web:
            def __init__(self):
                self.mock_responses = {}
                self.should_fail = False

            def set_url_response(self, url: str, body: str):
                self.mock_responses[url] = body

            def get(self, url: str):
                if self.should_fail:
                    raise RuntimeError("HTTP 403 Forbidden")
                if url in self.mock_responses:
                    return MockWebResponse(self.mock_responses[url])
                return MockWebResponse("// Default clean token code\ncontract Token {}")

    def get_contract_at(self, target_address):
        clean_addr = str(target_address).lower()
        if clean_addr in DEPLOYED_CONTRACTS_MOCK:
            return MockContractRef(DEPLOYED_CONTRACTS_MOCK[clean_addr])
        raise ValueError(f"No contract deployed at mock address {clean_addr}")

# Install mock into sys.modules
mock_gl = MockGL()
mock_module = type(sys)("genlayer")
mock_module.gl = mock_gl
mock_module.u256 = u256
mock_module.Address = Address
mock_module.TreeMap = TreeMap
sys.modules["genlayer"] = mock_module

# Import contracts
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "contracts")))
from project_disclosure_registry import ProjectDisclosureRegistry
from bytecode_audit_arbiter import BytecodeAuditArbiter

# =========================================================================
# TEST SUITE
# =========================================================================

class TestAuditDual(unittest.TestCase):

    def setUp(self):
        DEPLOYED_CONTRACTS_MOCK.clear()
        mock_gl.message.sender_address = Address("0x1111111111111111111111111111111111111111")
        mock_gl.nondet.web.mock_responses.clear()
        mock_gl.nondet.web.should_fail = False
        mock_gl.eq_principle.mock_decision = "VERIFIED_ACCURATE"
        mock_gl.eq_principle.mock_quote = "totalSupply = 1_000_000 * 10**18;"
        mock_gl.eq_principle.mock_rationale = "Code matches declared claims."

        # Setup Contract 1: ProjectDisclosureRegistry
        self.registry_addr = Address("0x1111111111111111111111111111111111111111")
        self.registry = ProjectDisclosureRegistry()
        self.registry.__init__()
        DEPLOYED_CONTRACTS_MOCK[str(self.registry_addr).lower()] = self.registry

        # Setup Contract 2: BytecodeAuditArbiter
        self.arbiter_addr = Address("0x2222222222222222222222222222222222222222")
        mock_gl.message.sender_address = self.arbiter_addr
        self.arbiter = BytecodeAuditArbiter()
        self.arbiter.__init__()
        DEPLOYED_CONTRACTS_MOCK[str(self.arbiter_addr).lower()] = self.arbiter

        # Registry owner binds arbiter
        mock_gl.message.sender_address = self.registry.owner
        self.registry.set_authorized_arbiter(self.arbiter_addr)

    def test_initialization_and_access_control(self):
        """Verify initial registry states and authorization guards."""
        self.assertEqual(int(self.registry.get_total_projects()), 0)
        self.assertEqual(int(self.arbiter.get_total_audits()), 0)
        self.assertEqual(str(self.registry.get_authorized_arbiter()).lower(), str(self.arbiter_addr).lower())

        # Non-owner cannot change arbiter
        attacker = Address("0x9999999999999999999999999999999999999999")
        mock_gl.message.sender_address = attacker
        with self.assertRaises(PermissionError):
            self.registry.set_authorized_arbiter(attacker)

    def test_register_project_validations(self):
        """Verify input validation when registering a project in Contract 1."""
        # Empty name
        with self.assertRaises(ValueError):
            self.registry.register_project("", "0x123", "https://url", "No mint")

        # Empty url
        with self.assertRaises(ValueError):
            self.registry.register_project("Token", "0x123", "", "No mint")

        # Empty claims
        with self.assertRaises(ValueError):
            self.registry.register_project("Token", "0x123", "https://url", "")

        # Valid registration
        pid = self.registry.register_project("HonestToken", "0x123", "https://raw.../honest.sol", "Fixed 1M supply, No mint")
        self.assertEqual(int(pid), 0)
        self.assertEqual(int(self.registry.get_total_projects()), 1)

        proj = self.registry.get_project(u256(0))
        self.assertEqual(proj["status"], "REGISTERED")

    def test_unauthorized_callback_rejected(self):
        """Verify Contract 1 update_audit_status cannot be called by unauthorized accounts."""
        self.registry.register_project("HonestToken", "0x123", "https://raw.../honest.sol", "No mint")
        
        # Attacker tries to directly mark project as VERIFIED_CLEAN
        mock_gl.message.sender_address = Address("0x9999999999999999999999999999999999999999")
        with self.assertRaises(PermissionError):
            self.registry.update_audit_status(u256(0), "VERIFIED_CLEAN", "fake quote", "fake notes")

    def test_cross_contract_audit_honest_token_success(self):
        """
        FULL INTERACTION TEST: HONEST TOKEN
        1. Creator registers HonestToken in Contract 1 claiming fixed supply & no mint.
        2. Contract 2 consumes Contract 1's state via .view().get_project(0).
        3. Contract 2 fetches honest_token.sol and validators confirm code matches disclosure.
        4. Contract 2 emits update to Contract 1 -> Project status becomes VERIFIED_CLEAN.
        """
        honest_code = """
        contract HonestToken {
            uint256 public totalSupply = 1_000_000 * 10**18;
            function transfer(address to, uint256 amount) public returns (bool) { return true; }
        }
        """
        url = "https://raw.githubusercontent.com/org/repo/commit1/honest_token.sol"
        mock_gl.nondet.web.set_url_response(url, honest_code)

        # 1. Register in Contract 1
        mock_gl.message.sender_address = Address("0x3333333333333333333333333333333333333333")
        pid = self.registry.register_project("HonestToken", "0xToken1", url, "Fixed 1,000,000 supply; no mint function; 0% tax")

        # 2. Trigger audit from Contract 2
        mock_gl.message.sender_address = self.arbiter_addr
        verdict = self.arbiter.audit_project(self.registry_addr, pid)
        self.assertEqual(verdict, "VERIFIED_ACCURATE")

        # 3. Verify Contract 2 audit record
        audit = self.arbiter.get_audit(u256(0))
        self.assertEqual(audit["verdict"], "VERIFIED_ACCURATE")
        self.assertEqual(audit["verbatim_quote"], "totalSupply = 1_000_000 * 10**18;")

        # 4. Verify Contract 1 status was updated via cross-contract callback
        proj = self.registry.get_project(pid)
        self.assertEqual(proj["status"], "VERIFIED_CLEAN")
        self.assertIn("totalSupply", proj["audit_quote"])

    def test_cross_contract_audit_deceptive_honeypot_flagged(self):
        """
        ADVERSARIAL INJECTION & BACKDOOR DEFENSE:
        1. Creator registers DeceptiveToken in Contract 1 claiming 'Fixed supply, No mint'.
        2. Contract 2 audits deceptive_honeypot.sol containing hidden 'function mint(...) public onlyOwner'.
        3. Validators detect backdoor -> verdict is DECEPTIVE_DISCLOSURE.
        4. Cross-contract call flips Contract 1 status to FLAGGED_DECEPTIVE with exact code quote!
        """
        honeypot_code = """
        contract DeceptiveToken {
            uint256 public totalSupply = 1_000_000 * 10**18;
            address public owner;
            // HIDDEN BACKDOOR:
            function mint(address to, uint256 amount) public onlyOwner returns (bool) {
                totalSupply += amount;
                return true;
            }
        }
        """
        url = "https://raw.githubusercontent.com/org/repo/commit2/deceptive_honeypot.sol"
        mock_gl.nondet.web.set_url_response(url, honeypot_code)

        # 1. Register deceptive project in Contract 1
        mock_gl.message.sender_address = Address("0x4444444444444444444444444444444444444444")
        pid = self.registry.register_project("DeceptiveToken", "0xToken2", url, "Community token; 100% Fixed supply; No mint function")

        # 2. Trigger audit from Contract 2
        mock_gl.message.sender_address = self.arbiter_addr
        verdict = self.arbiter.audit_project(self.registry_addr, pid)
        self.assertEqual(verdict, "DECEPTIVE_DISCLOSURE")

        # 3. Verify Contract 2 audit record
        audit = self.arbiter.get_audit(u256(0))
        self.assertEqual(audit["verdict"], "DECEPTIVE_DISCLOSURE")
        self.assertIn("function mint", audit["verbatim_quote"])

        # 4. Verify Contract 1 status was flipped to FLAGGED_DECEPTIVE
        proj = self.registry.get_project(pid)
        self.assertEqual(proj["status"], "FLAGGED_DECEPTIVE")
        self.assertIn("function mint", proj["audit_quote"])

    def test_evidence_failures_fail_closed(self):
        """Verify network errors or empty files cleanly fail closed."""
        url = "https://raw.githubusercontent.com/org/repo/commit3/empty.sol"
        mock_gl.nondet.web.set_url_response(url, "") # Empty source

        pid = self.registry.register_project("BrokenToken", "0xToken3", url, "No mint")
        
        mock_gl.message.sender_address = self.arbiter_addr
        verdict = self.arbiter.audit_project(self.registry_addr, pid)
        self.assertEqual(verdict, "DECEPTIVE_DISCLOSURE")

        proj = self.registry.get_project(pid)
        self.assertEqual(proj["status"], "FLAGGED_DECEPTIVE")

if __name__ == "__main__":
    unittest.main()
