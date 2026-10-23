from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx


class ScanType(Enum):
    SAST = "sast"
    DAST = "dast"
    SCA = "sca"  # Software Composition Analysis
    SECRETS = "secrets"
    CONTAINER = "container"
    IAC = "iac"  # Infrastructure as Code
    DEPENDENCY = "dependency"


class Severity(Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


@dataclass
class SecurityFinding:
    """A security finding from a scan."""
    id: str
    scan_type: ScanType
    severity: Severity
    title: str
    description: str
    file_path: str = ""
    line_start: int = 0
    line_end: int = 0
    rule_id: str = ""
    rule_name: str = ""
    cwe: str = ""
    cve: str = ""
    cvss_score: float = 0.0
    confidence: str = "high"  # high, medium, low
    fix_suggestion: str = ""
    references: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class ScanResult:
    """Result of a security scan."""
    scan_id: str
    scan_type: ScanType
    target: str
    started_at: datetime
    completed_at: datetime | None = None
    status: str = "running"  # running, completed, failed
    findings: list[SecurityFinding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class SecurityScanner:
    """Base class for security scanners."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
    
    async def scan(self, target: str | None = None) -> ScanResult:
        raise NotImplementedError
    
    async def scan_file(self, file_path: Path) -> list[SecurityFinding]:
        raise NotImplementedError


class SemgrepScanner(SecurityScanner):
    """Semgrep SAST scanner."""
    
    def __init__(self, workspace_root: Path, config: str = "auto"):
        super().__init__(workspace_root)
        self.semgrep_path = self._find_semgrep()
        self.config = config
    
    def _find_semgrep(self) -> str | None:
        for path in ["/usr/bin/semgrep", "/usr/local/bin/semgrep", os.path.expanduser("~/.local/bin/semgrep")]:
            if os.path.exists(path):
                return path
        return None
    
    async def scan(self, target: str | None = None) -> ScanResult:
        scan_id = f"semgrep-{uuid.uuid4().hex[:8]}"
        target_path = Path(target) if target else self.workspace_root
        
        result = ScanResult(
            scan_id=scan_id,
            scan_type=ScanType.SAST,
            target=str(target_path),
            started_at=datetime.now(),
        )
        
        if not self.semgrep_path:
            result.status = "failed"
            result.metadata["error"] = "semgrep not found"
            return result
        
        try:
            cmd = [self.semgrep_path, "scan", "--json", "--config", self.config]
            if target:
                cmd.append(str(target))
            else:
                cmd.append(str(self.workspace_root))
            
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if proc.returncode in (0, 1):  # 0 = no findings, 1 = findings found
                data = json.loads(proc.stdout)
                for finding in data.get("results", []):
                    result.findings.append(self._parse_finding(finding))
            
            result.status = "completed"
            result.completed_at = datetime.now()
            result.summary = self._summarize(result.findings)
            
        except Exception as e:
            result.status = "failed"
            result.metadata["error"] = str(e)
        
        return result
    
    def _parse_finding(self, finding: dict) -> SecurityFinding:
        return SecurityFinding(
            id=finding.get("fingerprint", ""),
            scan_type=ScanType.SAST,
            severity=Severity(finding.get("extra", {}).get("severity", "medium").lower()),
            title=finding.get("extra", {}).get("message", "Semgrep finding"),
            description=finding.get("extra", {}).get("message", ""),
            file_path=finding.get("path", ""),
            line_start=finding.get("start", {}).get("line", 0),
            line_end=finding.get("end", {}).get("line", 0),
            rule_id=finding.get("check_id", ""),
            rule_name=finding.get("extra", {}).get("metadata", {}).get("name", ""),
            cwe=finding.get("extra", {}).get("metadata", {}).get("cwe", ""),
            fix_suggestion=finding.get("extra", {}).get("fix", ""),
            references=[finding.get("extra", {}).get("metadata", {}).get("references", "")],
            metadata={"semgrep": finding},
        )
    
    def _summarize(self, findings: list[SecurityFinding]) -> dict:
        summary = {s.value: 0 for s in Severity}
        for f in findings:
            summary[f.severity.value] += 1
        summary["total"] = len(findings)
        return summary


class TrivyScanner(SecurityScanner):
    """Trivy vulnerability scanner for containers, dependencies, and IaC."""
    
    def __init__(self, workspace_root: Path):
        super().__init__(workspace_root)
        self.trivy_path = self._find_trivy()
    
    def _find_trivy(self) -> str | None:
        for path in ["/usr/bin/trivy", "/usr/local/bin/trivy", os.path.expanduser("~/.local/bin/trivy")]:
            if os.path.exists(path):
                return path
        return None
    
    async def scan_fs(self, target: str | None = None) -> ScanResult:
        """Scan filesystem for vulnerabilities."""
        scan_id = f"trivy-fs-{uuid.uuid4().hex[:8]}"
        target_path = Path(target) if target else self.workspace_root
        
        result = ScanResult(
            scan_id=scan_id,
            scan_type=ScanType.SCA,
            target=str(target_path),
            started_at=datetime.now(),
        )
        
        if not self.trivy_path:
            result.status = "failed"
            result.metadata["error"] = "trivy not found"
            return result
        
        try:
            cmd = [self.trivy_path, "fs", "--format", "json", "--severity", "CRITICAL,HIGH,MEDIUM,LOW"]
            if target:
                cmd.append(str(target))
            else:
                cmd.append(str(self.workspace_root))
            
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if proc.returncode in (0, 1):
                data = json.loads(proc.stdout)
                for result_item in data.get("Results", []):
                    for vuln in result_item.get("Vulnerabilities", []):
                        finding = SecurityFinding(
                            id=vuln.get("VulnerabilityID", ""),
                            scan_type=ScanType.SCA,
                            severity=self._map_severity(vuln.get("Severity", "")),
                            title=vuln.get("Title", vuln.get("VulnerabilityID", "")),
                            description=vuln.get("Description", ""),
                            file_path=result_item.get("Target", ""),
                            line_start=0,
                            rule_id=vuln.get("VulnerabilityID", ""),
                            cve=vuln.get("VulnerabilityID", ""),
                            cvss_score=vuln.get("CVSS", {}).get("nvd", {}).get("V3Score", 0.0),
                            fix_suggestion=f"Upgrade to {vuln.get('FixedVersion', 'latest')}",
                            references=vuln.get("References", []),
                            metadata={"trivy": vuln},
                        )
                        result.findings.append(finding)
            
            result.status = "completed"
            result.completed_at = datetime.now()
            result.summary = self._summarize(result.findings)
            
        except Exception as e:
            result.status = "failed"
            result.metadata["error"] = str(e)
        
        return result
    
    async def scan_image(self, image: str) -> ScanResult:
        """Scan container image."""
        scan_id = f"trivy-image-{uuid.uuid4().hex[:8]}"
        result = ScanResult(
            scan_id=scan_id,
            scan_type=ScanType.CONTAINER,
            target=image,
            started_at=datetime.now(),
        )
        
        if not self.trivy_path:
            result.status = "failed"
            result.metadata["error"] = "trivy not found"
            return result
        
        try:
            cmd = [self.trivy_path, "image", "--format", "json", "--severity", "CRITICAL,HIGH,MEDIUM,LOW", image]
            
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if proc.returncode in (0, 1):
                data = json.loads(proc.stdout)
                for result_item in data.get("Results", []):
                    for vuln in result_item.get("Vulnerabilities", []):
                        result.findings.append(SecurityFinding(
                            id=vuln.get("VulnerabilityID", ""),
                            scan_type=ScanType.CONTAINER,
                            severity=self._map_severity(vuln.get("Severity", "")),
                            title=vuln.get("Title", vuln.get("VulnerabilityID", "")),
                            description=vuln.get("Description", ""),
                            file_path=image,
                            rule_id=vuln.get("VulnerabilityID", ""),
                            cve=vuln.get("VulnerabilityID", ""),
                            cvss_score=vuln.get("CVSS", {}).get("nvd", {}).get("V3Score", 0.0),
                            fix_suggestion=f"Upgrade to {vuln.get('FixedVersion', 'latest')}",
                            references=vuln.get("References", []),
                            metadata={"trivy": vuln},
                        ))
            
            result.status = "completed"
            result.completed_at = datetime.now()
            result.summary = self._summarize(result.findings)
            
        except Exception as e:
            result.status = "failed"
            result.metadata["error"] = str(e)
        
        return result
    
    async def scan_iac(self, target: str | None = None) -> ScanResult:
        """Scan Infrastructure as Code."""
        scan_id = f"trivy-iac-{uuid.uuid4().hex[:8]}"
        target_path = Path(target) if target else self.workspace_root
        
        result = ScanResult(
            scan_id=scan_id,
            scan_type=ScanType.IAC,
            target=str(target_path),
            started_at=datetime.now(),
        )
        
        if not self.trivy_path:
            result.status = "failed"
            return result
        
        try:
            cmd = [self.trivy_path, "config", "--format", "json", str(target_path)]
            
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
            )
            
            if proc.returncode in (0, 1):
                data = json.loads(proc.stdout)
                for result_item in data.get("Results", []):
                    for misconf in result_item.get("Misconfigurations", []):
                        result.findings.append(SecurityFinding(
                            id=misconf.get("ID", ""),
                            scan_type=ScanType.IAC,
                            severity=self._map_severity(misconf.get("Severity", "")),
                            title=misconf.get("Title", ""),
                            description=misconf.get("Description", ""),
                            file_path=misconf.get("FilePath", ""),
                            line_start=misconf.get("Line", 0),
                            rule_id=misconf.get("ID", ""),
                            cwe=misconf.get("CWE", ""),
                            fix_suggestion=misconf.get("Resolution", ""),
                            references=misconf.get("References", []),
                            metadata={"trivy": misconf},
                        ))
            
            result.status = "completed"
            result.completed_at = datetime.now()
            result.summary = self._summarize(result.findings)
            
        except Exception as e:
            result.status = "failed"
            result.metadata["error"] = str(e)
        
        return result
    
    def _map_severity(self, severity: str) -> Severity:
        mapping = {
            "CRITICAL": Severity.CRITICAL,
            "HIGH": Severity.HIGH,
            "MEDIUM": Severity.MEDIUM,
            "LOW": Severity.LOW,
            "UNKNOWN": Severity.INFO,
        }
        return mapping.get(severity.upper(), Severity.INFO)
    
    def _summarize(self, findings: list[SecurityFinding]) -> dict:
        summary = {s.value: 0 for s in Severity}
        for f in findings:
            summary[f.severity.value] += 1
        summary["total"] = len(findings)
        return summary


class GitleaksScanner(SecurityScanner):
    """Gitleaks secrets scanner."""
    
    def __init__(self, workspace_root: Path):
        super().__init__(workspace_root)
        self.gitleaks_path = self._find_gitleaks()
    
    def _find_gitleaks(self) -> str | None:
        for path in ["/usr/bin/gitleaks", "/usr/local/bin/gitleaks", os.path.expanduser("~/.local/bin/gitleaks")]:
            if os.path.exists(path):
                return path
        return None
    
    async def scan(self, target: str | None = None) -> ScanResult:
        scan_id = f"gitleaks-{uuid.uuid4().hex[:8]}"
        target_path = Path(target) if target else self.workspace_root
        
        result = ScanResult(
            scan_id=scan_id,
            scan_type=ScanType.SECRETS,
            target=str(target_path),
            started_at=datetime.now(),
        )
        
        if not self.gitleaks_path:
            result.status = "failed"
            result.metadata["error"] = "gitleaks not found"
            return result
        
        try:
            cmd = [self.gitleaks_path, "detect", "--report-format", "json", "--source", str(target_path)]
            
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
            )
            
            if proc.returncode in (0, 1):
                data = json.loads(proc.stdout)
                for finding in data:
                    result.findings.append(SecurityFinding(
                        id=finding.get("RuleID", ""),
                        scan_type=ScanType.SECRETS,
                        severity=self._map_severity(finding.get("Severity", "")),
                        title=f"Secret detected: {finding.get('RuleID', '')}",
                        description=finding.get("Description", ""),
                        file_path=finding.get("File", ""),
                        line_start=finding.get("StartLine", 0),
                        line_end=finding.get("EndLine", 0),
                        rule_id=finding.get("RuleID", ""),
                        cwe="CWE-798",
                        fix_suggestion="Remove secret and rotate credentials",
                        references=["https://owasp.org/www-project-top-ten/2021/A07_2021-Identification_and_Authentication_Failures"],
                        metadata={"gitleaks": finding},
                    ))
            
            result.status = "completed"
            result.completed_at = datetime.now()
            result.summary = self._summarize(result.findings)
            
        except Exception as e:
            result.status = "failed"
            result.metadata["error"] = str(e)
        
        return result
    
    def _map_severity(self, severity: str) -> Severity:
        mapping = {
            "HIGH": Severity.HIGH,
            "MEDIUM": Severity.MEDIUM,
            "LOW": Severity.LOW,
        }
        return mapping.get(severity.upper(), Severity.INFO)


class BanditScanner(SecurityScanner):
    """Bandit Python SAST scanner."""
    
    def __init__(self, workspace_root: Path):
        super().__init__(workspace_root)
    
    async def scan(self, target: str | None = None) -> ScanResult:
        scan_id = f"bandit-{uuid.uuid4().hex[:8]}"
        target_path = Path(target) if target else self.workspace_root
        
        result = ScanResult(
            scan_id=scan_id,
            scan_type=ScanType.SAST,
            target=str(target_path),
            started_at=datetime.now(),
        )
        
        try:
            cmd = ["bandit", "-r", "-f", "json", str(target_path)]
            
            proc = await asyncio.to_thread(
                subprocess.run,
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
            )
            
            if proc.returncode in (0, 1):
                data = json.loads(proc.stdout)
                for finding in data.get("results", []):
                    result.findings.append(SecurityFinding(
                        id=finding.get("fingerprint", ""),
                        scan_type=ScanType.SAST,
                        severity=self._map_severity(finding.get("severity", "")),
                        title=finding.get("test_name", ""),
                        description=finding.get("issue_text", ""),
                        file_path=finding.get("filename", ""),
                        line_start=finding.get("line_number", 0),
                        line_end=finding.get("line_number", 0),
                        rule_id=finding.get("test_id", ""),
                        cwe=finding.get("cwe", {}).get("id", "") if finding.get("cwe") else "",
                        fix_suggestion=finding.get("more_info", ""),
                        metadata={"bandit": finding},
                    ))
            
            result.status = "completed"
            result.completed_at = datetime.now()
            result.summary = self._summarize(result.findings)
            
        except Exception as e:
            result.status = "failed"
            result.metadata["error"] = str(e)
        
        return result
    
    def _map_severity(self, severity: str) -> Severity:
        mapping = {
            "HIGH": Severity.HIGH,
            "MEDIUM": Severity.MEDIUM,
            "LOW": Severity.LOW,
        }
        return mapping.get(severity.upper(), Severity.INFO)


class SecurityOrchestrator:
    """Orchestrates multiple security scanners."""
    
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.scanners: dict[ScanType, SecurityScanner] = {
            ScanType.SAST: SemgrepScanner(workspace_root),
            ScanType.SCA: TrivyScanner(workspace_root),
            ScanType.CONTAINER: TrivyScanner(workspace_root),
            ScanType.IAC: TrivyScanner(workspace_root),
            ScanType.SECRETS: GitleaksScanner(workspace_root),
            ScanType.SAST: BanditScanner(workspace_root),  # Additional Python SAST
        }
    
    async def run_all_scans(self, target: str | None = None) -> dict[ScanType, ScanResult]:
        """Run all available scans."""
        results = {}
        
        # Run scans in parallel
        tasks = []
        for scan_type, scanner in self.scanners.items():
            if scan_type == ScanType.SAST:
                tasks.append(("sast", scanner.scan(target)))
            elif scan_type == ScanType.SCA:
                tasks.append(("sca", scanner.scan_fs(target)))
            elif scan_type == ScanType.CONTAINER:
                # Would need image name
                pass
            elif scan_type == ScanType.IAC:
                tasks.append(("iac", scanner.scan_iac(target)))
            elif scan_type == ScanType.SECRETS:
                tasks.append(("secrets", scanner.scan(target)))
        
        results_list = await asyncio.gather(*[t[1] for t in tasks], return_exceptions=True)
        
        for i, (name, _) in enumerate(tasks):
            if isinstance(results_list[i], Exception):
                results[ScanType[name.upper()]] = ScanResult(
                    scan_id=f"{name}-error",
                    scan_type=ScanType[name.upper()],
                    target="",
                    started_at=datetime.now(),
                    status="failed",
                    metadata={"error": str(results_list[i])},
                )
            else:
                results[ScanType[name.upper()]] = results_list[i]
        
        return results
    
    async def scan_pr(self, pr_number: int, repo: str) -> ScanResult:
        """Scan a PR for security issues."""
        # This would integrate with GitHub/GitLab API to get PR changes
        # and run targeted scans on changed files
        pass
    
    def get_consolidated_report(self, results: dict[ScanType, ScanResult]) -> dict:
        """Generate consolidated security report."""
        all_findings = []
        total_by_severity = {s.value: 0 for s in Severity}
        
        for scan_type, result in results.items():
            for finding in result.findings:
                all_findings.append(finding)
                total_by_severity[finding.severity.value] += 1
        
        # Sort by severity
        severity_order = {s.value: i for i, s in enumerate(Severity)}
        all_findings.sort(key=lambda f: severity_order.get(f.severity.value, 99))
        
        return {
            "scan_timestamp": datetime.now().isoformat(),
            "total_findings": len(all_findings),
            "by_severity": total_by_severity,
            "by_type": {k.value: len(v.findings) for k, v in results.items()},
            "findings": [
                {
                    "id": f.id,
                    "type": f.scan_type.value,
                    "severity": f.severity.value,
                    "title": f.title,
                    "file": f.file_path,
                    "line": f.line_start,
                    "rule": f.rule_id,
                    "cwe": f.cwe,
                    "cve": f.cve,
                    "fix": f.fix_suggestion,
                }
                for f in all_findings
            ],
        }


class OmniscanIntegration:
    """Integration with Omniscan for advanced threat detection."""
    
    def __init__(self, api_key: str = "", endpoint: str = "https://api.omniscan.io"):
        self.api_key = api_key
        self.endpoint = endpoint
        self.client = httpx.AsyncClient(timeout=60.0)
    
    async def scan_code(self, code: str, language: str) -> dict:
        """Scan code with Omniscan AI."""
        if not self.api_key:
            return {"error": "Omniscan API key not configured"}
        
        headers = {"Authorization": f"Bearer {self.api_key}"}
        payload = {"code": code, "language": language}
        
        try:
            response = await self.client.post(
                f"{self.endpoint}/v1/scan/code",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def scan_dependencies(self, dependencies: list[dict]) -> dict:
        """Scan dependencies for vulnerabilities."""
        if not self.api_key:
            return {"error": "Omniscan API key not configured"}
        
        try:
            response = await self.client.post(
                f"{self.endpoint}/v1/scan/dependencies",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"dependencies": dependencies},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}
    
    async def get_threat_intel(self, cve_ids: list[str]) -> dict:
        """Get threat intelligence for CVEs."""
        if not self.api_key:
            return {"error": "Omniscan API key not configured"}
        
        try:
            response = await self.client.post(
                f"{self.endpoint}/v1/intel/threats",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"cve_ids": cve_ids},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}


class MultiChainFramework:
    """Multi-Chain Framework for blockchain security analysis."""
    
    SUPPORTED_CHAINS = [
        "ethereum",
        "polygon",
        "arbitrum",
        "optimism",
        "base",
        "avalanche",
        "bsc",
        "fantom",
        "gnosis",
        "solana",
        "aptos",
        "sui",
    ]
    
    def __init__(self, rpc_urls: dict[str, str] = None, api_keys: dict[str, str] = None):
        self.rpc_urls = rpc_urls or {}
        self.api_keys = api_keys or {}
        self.client = httpx.AsyncClient(timeout=30.0)
    
    async def scan_contract(self, chain: str, address: str) -> dict:
        """Scan smart contract for vulnerabilities."""
        if chain not in self.SUPPORTED_CHAINS:
            return {"error": f"Unsupported chain: {chain}"}
        
        rpc_url = self.rpc_urls.get(chain)
        if not rpc_url:
            return {"error": f"No RPC URL configured for {chain}"}
        
        # Get contract code
        code = await self._get_contract_code(rpc_url, address)
        if not code:
            return {"error": "Contract not found or no code"}
        
        # Analyze with Slither-like checks
        findings = self._analyze_contract(code)
        
        return {
            "chain": chain,
            "address": address,
            "code_hash": hashlib.sha256(code.encode()).hexdigest()[:16],
            "findings": findings,
            "risk_score": self._calculate_risk_score(findings),
        }
    
    async def _get_contract_code(self, rpc_url: str, address: str) -> str:
        payload = {
            "jsonrpc": "2.0",
            "method": "eth_getCode",
            "params": [address, "latest"],
            "id": 1,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(rpc_url, json=payload)
            data = response.json()
            return data.get("result", "")
    
    def _analyze_contract(self, code: str) -> list[dict]:
        """Basic static analysis of Solidity code."""
        findings = []
        
        # Check for common vulnerabilities
        checks = [
            (r"selfdestruct\s*\(", "Selfdestruct usage", "HIGH"),
            (r"delegatecall\s*\(", "Delegatecall usage", "HIGH"),
            (r"\.call\{value:", "Low-level call with value", "MEDIUM"),
            (r"tx\.origin", "tx.origin usage", "HIGH"),
            (r"block\.timestamp", "Block timestamp dependency", "MEDIUM"),
            (r"block\.number", "Block number dependency", "LOW"),
            (r"assembly\s*{", "Inline assembly", "MEDIUM"),
            (r"require\s*\(.*msg\.sender", "Missing access control", "HIGH"),
            (r"payable\s+function", "Payable function", "INFO"),
        ]
        
        for pattern, title, severity in checks:
            for match in re.finditer(pattern, code):
                findings.append({
                    "type": "static_analysis",
                    "title": title,
                    "severity": severity,
                    "line": code[:match.start()].count("\n") + 1,
                    "code_snippet": code[max(0, match.start()-50):match.end()+50],
                    "recommendation": f"Review {title.lower()} usage",
                })
        
        return findings
    
    def _calculate_risk_score(self, findings: list[dict]) -> float:
        severity_weights = {"CRITICAL": 10, "HIGH": 7, "MEDIUM": 4, "LOW": 2, "INFO": 1}
        total = sum(severity_weights.get(f.get("severity", "INFO"), 1) for f in findings)
        return min(total / 100.0, 1.0)
    
    async def monitor_transactions(self, chain: str, address: str, callback: callable):
        """Monitor transactions to/from an address."""
        # Would use WebSocket or polling
        pass
    
    async def analyze_token(self, chain: str, token_address: str) -> dict:
        """Analyze ERC-20/SPL token for rugpull/honeypot risks."""
        code = await self._get_contract_code(self.rpc_urls.get(chain, ""), token_address)
        
        # Check for honeypot patterns
        honeypot_patterns = [
            (r"balanceOf\[msg\.sender\]\s*[=<>]", "Balance manipulation"),
            (r"transferFrom.*msg\.sender", "Transfer from sender"),
            (r"allowance\[.*\]\s*=", "Allowance manipulation"),
        ]
        
        risks = []
        for pattern, desc in honeypot_patterns:
            if re.search(pattern, code):
                risks.append({"type": "honeypot_risk", "description": desc, "severity": "HIGH"})
        
        return {
            "token": token_address,
            "chain": chain,
            "is_honeypot": len(risks) > 0,
            "risks": risks,
        }


class SecurityReportGenerator:
    """Generates comprehensive security reports."""
    
    def __init__(self):
        self.templates = {}
    
    def generate_html_report(self, orchestrator_results: dict, output_path: str):
        """Generate HTML security report."""
        html = self._generate_html(orchestrator_results)
        with open(output_path, "w") as f:
            f.write(html)
    
    def generate_pdf_report(self, orchestrator_results: dict, output_path: str):
        """Generate PDF security report (requires weasyprint)."""
        html = self._generate_html(orchestrator_results)
        try:
            from weasyprint import HTML
            HTML(string=html).write_pdf(output_path)
        except ImportError:
            raise ImportError("weasyprint not installed")
    
    def generate_sarif(self, orchestrator_results: dict, output_path: str):
        """Generate SARIF report for IDE integration."""
        sarif = {
            "version": "2.1.0",
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "runs": [],
        }
        
        for scan_type, result in orchestrator_results.items():
            run = {
                "tool": {
                    "driver": {
                        "name": f"Bifang {scan_type.value.upper()}",
                        "informationUri": "https://bifang.dev",
                        "rules": [],
                    }
                },
                "results": [],
            }
            
            rule_map = {}
            for finding in result.findings:
                rule_id = finding.rule_id or finding.id
                if rule_id not in rule_map:
                    rule_map[rule_id] = {
                        "id": rule_id,
                        "name": finding.rule_name or finding.title,
                        "shortDescription": {"text": finding.title},
                        "fullDescription": {"text": finding.description},
                        "defaultConfiguration": {"level": self._severity_to_level(finding.severity)},
                        "helpUri": finding.references[0] if finding.references else "",
                    }
                
                run["results"].append({
                    "ruleId": rule_id,
                    "level": self._severity_to_level(finding.severity),
                    "message": {"text": finding.description},
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": finding.file_path},
                            "region": {
                                "startLine": finding.line_start,
                                "endLine": finding.line_end,
                            } if finding.line_start > 0 else {},
                        }
                    }],
                })
            
            run["tool"]["driver"]["rules"] = list(rule_map.values())
            sarif["runs"].append(run)
        
        with open(output_path, "w") as f:
            json.dump(sarif, f, indent=2)
    
    def _severity_to_level(self, severity: Severity) -> str:
        mapping = {
            Severity.CRITICAL: "error",
            Severity.HIGH: "error",
            Severity.MEDIUM: "warning",
            Severity.LOW: "note",
            Severity.INFO: "none",
        }
        return mapping.get(severity, "note")
    
    def _generate_html(self, results: dict) -> str:
        # Generate comprehensive HTML report
        consolidated = SecurityOrchestrator(None).get_consolidated_report(results)
        
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Bifang Security Report</title>
    <style>
        body {{ font-family: 'Inter', system-ui, sans-serif; background: #0F1728; color: #F7F7F7; margin: 0; padding: 2rem; }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{ text-align: center; margin-bottom: 2rem; }}
        .badge {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; margin: 0.25rem; }}
        .critical {{ background: #7F1D1D; color: #EF4444; }}
        .high {{ background: #7F1D1D; color: #EF4444; }}
        .medium {{ background: #78350F; color: #F59E0B; }}
        .low {{ background: #1E3A5F; color: #3B82F6; }}
        .info {{ background: #1E3A5F; color: #10B981; }}
        .finding {{ background: #1A2338; border: 1px solid #2D3A50; border-radius: 0.75rem; padding: 1.5rem; margin: 1rem 0; }}
        .finding-header {{ display: flex; justify-content: space-between; margin-bottom: 1rem; }}
        .finding-title {{ font-size: 1.125rem; font-weight: 600; }}
        .finding-meta {{ display: flex; gap: 1rem; font-size: 0.875rem; color: #A0A8B8; }}
        .code-block {{ background: #0F1728; border-radius: 0.5rem; padding: 1rem; overflow-x: auto; font-family: monospace; font-size: 0.875rem; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 2rem 0; }}
        .summary-card {{ background: #1A2338; border: 1px solid #2D3A50; border-radius: 0.75rem; padding: 1.5rem; text-align: center; }}
        .summary-value {{ font-size: 3rem; font-weight: 700; font-family: monospace; }}
        .critical {{ color: #EF4444; }}
        .high {{ color: #EF4444; }}
        .medium {{ color: #F59E0B; }}
        .low {{ color: #3B82F6; }}
        .total {{ color: #F7F7F7; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Bifang Security Report</h1>
            <p>Generated: {datetime.now().isoformat()}</p>
        </div>
        
        <div class="summary-grid">
            <div class="summary-card">
                <div class="summary-value total">{total_by_severity['total']}</div>
                <div>Total Findings</div>
            </div>
            <div class="summary-card">
                <div class="summary-value critical">{total_by_severity['critical']}</div>
                <div>Critical</div>
            </div>
            <div class="summary-card">
                <div class="summary-value high">{total_by_severity['high']}</div>
                <div>High</div>
            </div>
            <div class="summary-card">
                <div class="summary-value medium">{total_by_severity['medium']}</div>
                <div>Medium</div>
            </div>
            <div class="summary-card">
                <div class="summary-value low">{total_by_severity['low']}</div>
                <div>Low</div>
            </div>
            <div class="summary-card">
                <div class="summary-value info">{total_by_severity['info']}</div>
                <div>Info</div>
            </div>
        </div>
        
        <h2>Findings</h2>
        {findings_html}
    </div>
</body>
</html>"""
        
        # Generate findings HTML
        findings_html = ""
        for scan_type, result in results.items():
            if not result.findings:
                continue
            
            findings_html += f"<h3>{scan_type.value.upper()} ({len(result.findings)} findings)</h3>"
            for finding in result.findings:
                findings_html += f"""
                <div class="finding">
                    <div class="finding-header">
                        <span class="finding-title">{finding.title}</span>
                        <span class="badge {finding.severity.value.lower()}">{finding.severity.value.upper()}</span>
                    </div>
                    <div class="finding-meta">
                        <span>📁 {finding.file_path}:{finding.line_start}</span>
                        <span>🔍 {finding.rule_id}</span>
                        <span>📋 {finding.cwe or 'N/A'}</span>
                    </div>
                    <p>{finding.description}</p>
                    {f'<div class="code-block">{finding.metadata.get("code_snippet", "").replace("<", "<").replace(">", ">")}</div>' if finding.metadata.get("code_snippet") else ''}
                    <p><strong>Fix:</strong> {finding.fix_suggestion}</p>
                </div>
                """
        
        return html.format(
            total_by_severity=consolidated.get("by_severity", {}),
            findings_html=findings_html,
        )


async def create_security_orchestrator(workspace_root: Path) -> SecurityOrchestrator:
    return SecurityOrchestrator(workspace_root)