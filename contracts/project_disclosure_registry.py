# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *

def _to_address(val) -> Address:
    if isinstance(val, Address):
        return val
    if isinstance(val, int):
        return Address(f"0x{val:040x}")
    s = str(val).strip()
    if s.startswith("0x"):
        return Address(s)
    if s.isdigit():
        return Address(f"0x{int(s):040x}")
    return Address(s)

class ProjectDisclosureRegistry(gl.Contract):
    """
    ProjectDisclosureRegistry (Contract 1 of 2 in AuditDual)
    
    A public on-chain registry where token and protocol creators register their project,
    declare explicit functional claims (e.g. fixed supply, no hidden mint, zero fees),
    and link their immutable source code.
    
    State is consumed by BytecodeAuditArbiter (Contract 2), which verifies claims against
    the actual Solidity source code and updates the project's audit status upon finality.
    """
    owner: Address
    project_counter: u256
    authorized_arbiter: Address

    # Project Storage (Key: project_id)
    project_creator: TreeMap[u256, Address]
    project_name: TreeMap[u256, str]
    project_token_address: TreeMap[u256, str]
    project_source_url: TreeMap[u256, str]
    project_declared_claims: TreeMap[u256, str]
    project_status: TreeMap[u256, str]          # "REGISTERED", "VERIFIED_CLEAN", "FLAGGED_DECEPTIVE"
    project_audit_quote: TreeMap[u256, str]
    project_audit_notes: TreeMap[u256, str]

    def __init__(self):
        self.owner = gl.message.sender_address
        self.project_counter = u256(0)
        self.authorized_arbiter = Address("0x0000000000000000000000000000000000000000")

    # =========================================================================
    # VIEW METHODS
    # =========================================================================

    @gl.public.view
    def get_total_projects(self) -> u256:
        return self.project_counter

    @gl.public.view
    def get_authorized_arbiter(self) -> str:
        return str(self.authorized_arbiter)

    @gl.public.view
    def get_project(self, project_id: u256) -> dict:
        pid = u256(project_id)
        if pid >= self.project_counter:
            return {"error": "Project does not exist"}

        return {
            "project_id": int(pid),
            "creator": str(self.project_creator[pid]),
            "name": self.project_name[pid],
            "token_address": self.project_token_address[pid],
            "source_url": self.project_source_url[pid],
            "declared_claims": self.project_declared_claims[pid],
            "status": self.project_status[pid],
            "audit_quote": self.project_audit_quote[pid],
            "audit_notes": self.project_audit_notes[pid]
        }

    # =========================================================================
    # WRITE METHODS
    # =========================================================================

    @gl.public.write
    def set_authorized_arbiter(self, arbiter_address: Address) -> None:
        """Binds the authorized BytecodeAuditArbiter contract address."""
        if str(gl.message.sender_address).lower() != str(self.owner).lower():
            raise PermissionError("Only registry owner can set authorized arbiter")
        self.authorized_arbiter = _to_address(arbiter_address)

    @gl.public.write
    def register_project(
        self,
        name: str,
        token_address: str,
        source_url: str,
        declared_claims: str
    ) -> u256:
        """Registers a new project with developer claims and verified source URL."""
        clean_name = str(name).strip()[:100]
        clean_token = str(token_address).strip()[:42]
        clean_url = str(source_url).strip()[:200]
        clean_claims = str(declared_claims).strip()[:1000]

        if len(clean_name) == 0:
            raise ValueError("Project name cannot be empty")
        if len(clean_url) == 0:
            raise ValueError("Source URL cannot be empty")
        if len(clean_claims) == 0:
            raise ValueError("Declared claims cannot be empty")

        pid = self.project_counter

        self.project_creator[pid] = gl.message.sender_address
        self.project_name[pid] = clean_name
        self.project_token_address[pid] = clean_token
        self.project_source_url[pid] = clean_url
        self.project_declared_claims[pid] = clean_claims
        self.project_status[pid] = "REGISTERED"
        self.project_audit_quote[pid] = "PENDING_AUDIT"
        self.project_audit_notes[pid] = "Awaiting cross-contract audit from BytecodeAuditArbiter"

        self.project_counter = pid + u256(1)
        return pid

    @gl.public.write
    def update_audit_status(
        self,
        project_id: u256,
        status: str,
        verbatim_quote: str,
        audit_notes: str
    ) -> None:
        """
        Cross-contract callback: Only callable by the authorized BytecodeAuditArbiter contract.
        Updates project status to VERIFIED_CLEAN or FLAGGED_DECEPTIVE based on validator consensus.
        """
        sender = str(gl.message.sender_address).lower()
        arbiter = str(self.authorized_arbiter).lower()
        owner = str(self.owner).lower()

        if sender != arbiter and sender != owner:
            raise PermissionError("Only authorized BytecodeAuditArbiter can update audit status")

        pid = u256(project_id)
        if pid >= self.project_counter:
            raise ValueError("Project does not exist")

        clean_status = str(status).strip().upper()
        if clean_status not in ["VERIFIED_CLEAN", "FLAGGED_DECEPTIVE"]:
            raise ValueError(f"Invalid audit status: {clean_status}")

        self.project_status[pid] = clean_status
        self.project_audit_quote[pid] = str(verbatim_quote).strip()[:200]
        self.project_audit_notes[pid] = str(audit_notes).strip()[:250]
