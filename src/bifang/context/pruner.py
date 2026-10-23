from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .kv_store import KVStore, KVEntry
from ..config import Config
from ..tools import search, list_files, read_file
from ..workspace import Workspace
from ..policy import Policy


@dataclass
class CodeSnippet:
    """A relevant code snippet with metadata."""
    file_path: str
    start_line: int
    end_line: int
    content: str
    relevance_score: float
    snippet_type: str  # function, class, method, import, config, test
    symbols: list[str] = field(default_factory=list)  # Function/class names
    language: str = ""


@dataclass
class CodebaseMap:
    """A map of the codebase with indexed symbols and files."""
    files: dict[str, dict] = field(default_factory=dict)  # file_path -> file_info
    symbols: dict[str, list[str]] = field(default_factory=dict)  # symbol -> file_paths
    imports: dict[str, list[str]] = field(default_factory=dict)  # file -> imported modules
    dependencies: dict[str, list[str]] = field(default_factory=dict)  # file -> dependent files
    last_updated: float = 0
    total_files: int = 0
    total_lines: int = 0


class CodebaseIndexer:
    """Indexes a codebase for efficient context retrieval."""
    
    def __init__(self, workspace: Workspace, policy: Policy):
        self.workspace = workspace
        self.policy = policy
        self.codebase_map = CodebaseMap()
        self._file_cache: dict[str, str] = {}
        self._initialized = False
    
    async def index_workspace(self, force: bool = False) -> CodebaseMap:
        """Index the entire workspace."""
        if self._initialized and not force:
            return self.codebase_map
        
        self.codebase_map = CodebaseMap()
        self._file_cache.clear()
        
        # Get all files
        files_str = list_files(self.workspace.root, limit=5000)
        files = files_str.strip().split("\n") if files_str.strip() else []
        
        # Process files in parallel batches
        batch_size = 50
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            await asyncio.gather(*[
                self._index_file(f) for f in batch
            ])
        
        self.codebase_map.last_updated = time.time()
        self._initialized = True
        return self.codebase_map
    
    async def _index_file(self, file_path: str):
        """Index a single file."""
        try:
            full_path = self.workspace.root / file_path
            if not full_path.exists():
                return
            
            # Check if file should be skipped
            if self._should_skip_file(file_path):
                return
            
            content = await asyncio.to_thread(
                full_path.read_text, encoding="utf-8", errors="replace"
            )
            
            self._file_cache[file_path] = content
            lines = content.splitlines()
            
            # Extract file info
            file_info = {
                "path": file_path,
                "lines": len(lines),
                "size": len(content),
                "language": self._detect_language(file_path),
                "symbols": [],
                "imports": [],
            }
            
            # Extract symbols and imports based on language
            language = file_info["language"]
            if language == "python":
                symbols, imports = self._extract_python_symbols(content, file_path)
            elif language in ("javascript", "typescript"):
                symbols, imports = self._extract_js_symbols(content, file_path)
            elif language in ("rust",):
                symbols, imports = self._extract_rust_symbols(content, file_path)
            elif language in ("go",):
                symbols, imports = self._extract_go_symbols(content, file_path)
            else:
                symbols, imports = [], []
            
            file_info["symbols"] = symbols
            file_info["imports"] = imports
            
            # Update codebase map
            self.codebase_map.files[file_path] = file_info
            self.codebase_map.total_files += 1
            self.codebase_map.total_lines += len(lines)
            
            for symbol in symbols:
                if symbol not in self.codebase_map.symbols:
                    self.codebase_map.symbols[symbol] = []
                self.codebase_map.symbols[symbol].append(file_path)
            
            for imp in imports:
                if imp not in self.codebase_map.imports:
                    self.codebase_map.imports[imp] = []
                self.codebase_map.imports[imp].append(file_path)
            
        except Exception as e:
            print(f"Failed to index {file_path}: {e}")
    
    def _should_skip_file(self, file_path: str) -> bool:
        """Check if file should be skipped during indexing."""
        skip_patterns = [
            "__pycache__", ".git", ".venv", "node_modules", "dist", "build",
            ".pytest_cache", ".ruff_cache", "__pycache__", ".mypy_cache",
            ".coverage", "htmlcov", ".tox", "venv", "env",
        ]
        return any(pattern in file_path for pattern in skip_patterns)
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".r": "r",
            ".jl": "julia",
            ".lua": "lua",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".fish": "fish",
            ".ps1": "powershell",
            ".sql": "sql",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "scss",
            ".sass": "sass",
            ".less": "less",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".ini": "ini",
            ".cfg": "ini",
            ".conf": "ini",
            ".xml": "xml",
            ".md": "markdown",
            ".txt": "text",
        }
        return lang_map.get(ext, "unknown")
    
    def _extract_python_symbols(self, content: str, file_path: str) -> tuple[list[str], list[str]]:
        """Extract Python symbols (functions, classes) and imports."""
        symbols = []
        imports = []
        
        # Find imports
        import_pattern = re.compile(r'^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))', re.MULTILINE)
        for match in import_pattern.finditer(content):
            if match.group(1):
                imports.append(match.group(1))
            elif match.group(2):
                imports.append(match.group(2))
        
        # Find class definitions
        class_pattern = re.compile(r'^\s*class\s+(\w+)', re.MULTILINE)
        for match in class_pattern.finditer(content):
            symbols.append(f"class:{match.group(1)}")
        
        # Find function definitions
        func_pattern = re.compile(r'^\s*(?:async\s+)?def\s+(\w+)', re.MULTILINE)
        for match in func_pattern.finditer(content):
            symbols.append(f"func:{match.group(1)}")
        
        # Find async functions
        async_func_pattern = re.compile(r'^\s*async\s+def\s+(\w+)', re.MULTILINE)
        for match in async_func_pattern.finditer(content):
            symbols.append(f"async_func:{match.group(1)}")
        
        return symbols, list(set(imports))
    
    def _extract_js_symbols(self, content: str, file_path: str) -> tuple[list[str], list[str]]:
        """Extract JavaScript/TypeScript symbols and imports."""
        symbols = []
        imports = []
        
        # Find imports
        import_pattern = re.compile(r'^\s*import\s+(?:.*?\s+from\s+)?[\'"]([^\'"]+)[\'"]', re.MULTILINE)
        for match in import_pattern.finditer(content):
            imports.append(match.group(1))
        
        # Find function declarations
        func_pattern = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)', re.MULTILINE)
        for match in func_pattern.finditer(content):
            symbols.append(f"func:{match.group(1)}")
        
        # Find arrow functions
        arrow_pattern = re.compile(r'(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\(', re.MULTILINE)
        for match in arrow_pattern.finditer(content):
            symbols.append(f"arrow_func:{match.group(1)}")
        
        # Find class definitions
        class_pattern = re.compile(r'^\s*export\s+class\s+(\w+)', re.MULTILINE)
        for match in class_pattern.finditer(content):
            symbols.append(f"class:{match.group(1)}")
        
        return symbols, list(set(imports))
    
    def _extract_rust_symbols(self, content: str, file_path: str) -> tuple[list[str], list[str]]:
        """Extract Rust symbols and imports."""
        symbols = []
        imports = []
        
        # Find imports/use statements
        import_pattern = re.compile(r'^\s*use\s+([^;]+);', re.MULTILINE)
        for match in import_pattern.finditer(content):
            imports.append(match.group(1))
        
        # Find functions
        func_pattern = re.compile(r'(?:pub\s+)?(?:async\s+)?fn\s+(\w+)', re.MULTILINE)
        for match in func_pattern.finditer(content):
            symbols.append(f"fn:{match.group(1)}")
        
        # Find structs
        struct_pattern = re.compile(r'(?:pub\s+)?struct\s+(\w+)', re.MULTILINE)
        for match in struct_pattern.finditer(content):
            symbols.append(f"struct:{match.group(1)}")
        
        # Find enums
        enum_pattern = re.compile(r'(?:pub\s+)?enum\s+(\w+)', re.MULTILINE)
        for match in enum_pattern.finditer(content):
            symbols.append(f"enum:{match.group(1)}")
        
        # Find traits
        trait_pattern = re.compile(r'(?:pub\s+)?trait\s+(\w+)', re.MULTILINE)
        for match in trait_pattern.finditer(content):
            symbols.append(f"trait:{match.group(1)}")
        
        return symbols, list(set(imports))
    
    def _extract_go_symbols(self, content: str, file_path: str) -> tuple[list[str], list[str]]:
        """Extract Go symbols and imports."""
        symbols = []
        imports = []
        
        # Find imports
        import_pattern = re.compile(r'^\s*import\s+(?:"([^"]+)"|\(([^)]+)\))', re.MULTILINE)
        for match in import_pattern.finditer(content):
            if match.group(1):
                imports.append(match.group(1))
            elif match.group(2):
                for imp in match.group(2).split():
                    imports.append(imp.strip('"'))
        
        # Find functions
        func_pattern = re.compile(r'func\s+(?:\([^)]*\)\s+)?(\w+)', re.MULTILINE)
        for match in func_pattern.finditer(content):
            symbols.append(f"func:{match.group(1)}")
        
        # Find structs
        struct_pattern = re.compile(r'type\s+(\w+)\s+struct', re.MULTILINE)
        for match in struct_pattern.finditer(content):
            symbols.append(f"struct:{match.group(1)}")
        
        # Find interfaces
        interface_pattern = re.compile(r'type\s+(\w+)\s+interface', re.MULTILINE)
        for match in interface_pattern.finditer(content):
            symbols.append(f"interface:{match.group(1)}")
        
        return symbols, list(set(imports))


class ContextPruner:
    """Prunes context to relevant snippets using map-reduce approach."""
    
    def __init__(
        self,
        workspace: Workspace,
        policy: Policy,
        indexer: CodebaseIndexer,
        max_context_tokens: int = 100000,
    ):
        self.workspace = workspace
        self.policy = policy
        self.indexer = indexer
        self.max_context_tokens = max_context_tokens
    
    async def prune_context(
        self,
        query: str,
        current_files: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> list[CodeSnippet]:
        """Prune context to relevant snippets using map-reduce."""
        max_tokens = max_tokens or self.max_context_tokens
        
        # Ensure index is up to date
        await self.indexer.index_workspace()
        
        # Phase 1: MAP - Find relevant files and symbols
        relevant_files = await self._map_phase(query, current_files)
        
        # Phase 2: REDUCE - Extract relevant snippets from files
        snippets = await self._reduce_phase(query, relevant_files, max_tokens)
        
        return snippets
    
    async def _map_phase(
        self,
        query: str,
        current_files: list[str] | None,
    ) -> list[tuple[str, float]]:
        """Map phase: find relevant files and score them."""
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored_files = []
        
        for file_path, file_info in self.indexer.codebase_map.files.items():
            # Skip if not in current files (if specified)
            if current_files and file_path not in current_files:
                continue
            
            score = 0.0
            
            # Score based on filename
            file_name = Path(file_path).name.lower()
            for word in query_words:
                if word in file_name:
                    score += 2.0
            
            # Score based on symbols
            for symbol in file_info.get("symbols", []):
                symbol_name = symbol.split(":", 1)[-1].lower()
                for word in query_words:
                    if word in symbol_name:
                        score += 1.5
            
            # Score based on imports
            for imp in file_info.get("imports", []):
                for word in query_words:
                    if word in imp.lower():
                        score += 1.0
            
            # Score based on file content (sample)
            content = self._get_file_content(file_path)
            if content:
                content_lower = content.lower()
                for word in query_words:
                    if word in content_lower:
                        score += 0.5
            
            # Boost if file is in current_files
            if current_files and file_path in current_files:
                score += 3.0
            
            if score > 0:
                scored_files.append((file_path, score))
        
        # Sort by score descending
        scored_files.sort(key=lambda x: x[1], reverse=True)
        return scored_files[:50]  # Top 50 files
    
    def _get_file_content(self, file_path: str) -> str:
        """Get file content from cache or disk."""
        if file_path in self.indexer._file_cache:
            return self.indexer._file_cache[file_path]
        
        try:
            full_path = self.workspace.root / file_path
            if full_path.exists():
                content = full_path.read_text(encoding="utf-8", errors="replace")
                self.indexer._file_cache[file_path] = content
                return content
        except Exception:
            pass
        return ""
    
    async def _reduce_phase(
        self,
        query: str,
        scored_files: list[tuple[str, float]],
        max_tokens: int,
    ) -> list[CodeSnippet]:
        """Reduce phase: extract relevant snippets from scored files."""
        snippets = []
        token_budget = max_tokens
        
        for file_path, file_score in scored_files:
            if token_budget <= 0:
                break
            
            content = self._get_file_content(file_path)
            if not content:
                continue
            
            # Extract relevant snippets from this file
            file_snippets = await self._extract_snippets_from_file(
                file_path, content, query, token_budget
            )
            
            for snippet in file_snippets:
                snippet_tokens = self._estimate_tokens(snippet.content)
                if token_budget >= snippet_tokens:
                    snippets.append(snippet)
                    token_budget -= snippet_tokens
                else:
                    # Try to fit a truncated version
                    truncated = self._truncate_snippet(snippet, token_budget)
                    if truncated:
                        snippets.append(truncated)
                    break
        
        return snippets
    
    async def _extract_snippets_from_file(
        self,
        file_path: str,
        content: str,
        query: str,
        token_budget: int,
    ) -> list[CodeSnippet]:
        """Extract relevant snippets from a single file."""
        snippets = []
        lines = content.splitlines()
        query_lower = query.lower()
        query_words = set(query.lower().split())
        
        # Find relevant line ranges
        relevant_lines = []
        
        for i, line in enumerate(lines):
            line_lower = line.lower()
            score = 0
            
            for word in query.split():
                if word.lower() in line_lower:
                    score += 1
            
            if score > 0:
                relevant_lines.append((i, score))
        
        if not relevant_lines:
            return []
        
        # Merge nearby lines into ranges
        merged_ranges = []
        current_start = relevant_lines[0][0]
        current_end = relevant_lines[0][0]
        current_score = relevant_lines[0][1]
        
        for line_idx, score in relevant_lines[1:]:
            if line_idx <= current_end + 5:  # Merge if within 5 lines
                current_end = line_idx
                current_score = max(current_score, score)
            else:
                merged_ranges.append((current_start, current_end, current_score))
                current_start = line_idx
                current_end = line_idx
                current_score = score
        
        merged_ranges.append((current_start, current_end, current_score))
        
        # Extract snippets from merged ranges
        for start, end, score in merged_ranges:
            # Add context lines
            context_lines = 3
            start = max(0, start - context_lines)
            end = min(len(lines) - 1, end + context_lines)
            
            snippet_content = "\n".join(lines[start:end+1])
            snippet_tokens = self._estimate_tokens(snippet_content)
            
            # Determine snippet type
            snippet_type = self._determine_snippet_type(lines[start:end+1])
            symbols = self._extract_symbols_from_lines(lines[start:end+1])
            
            snippet = CodeSnippet(
                file_path=file_path,
                start_line=start + 1,
                end_line=end + 1,
                content=snippet_content,
                relevance_score=score,
                snippet_type=snippet_type,
                symbols=symbols,
                language=self._detect_language(file_path),
            )
            snippets.append(snippet)
        
        return snippets
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
    
    def _determine_snippet_type(self, lines: list[str]) -> str:
        """Determine the type of code snippet."""
        content = "\n".join(lines).lower()
        
        if any(kw in content for kw in ["def ", "async def ", "function ", "func "]):
            return "function"
        elif "class " in content:
            return "class"
        elif any(kw in content for kw in ["import ", "from ", "use ", "require(", "#include"]):
            return "import"
        elif any(kw in content for kw in ["test_", "assert", "expect(", "describe(", "it("]):
            return "test"
        elif any(kw in content for kw in ["config", "settings", "env", ".env", "yaml", "toml", "json"]):
            return "config"
        else:
            return "code"
    
    def _extract_symbols_from_lines(self, lines: list[str]) -> list[str]:
        """Extract symbols from lines."""
        symbols = []
        content = "\n".join(lines)
        
        # Python
        for match in re.finditer(r'(?:def|class)\s+(\w+)', content):
            symbols.append(match.group(1))
        # JS/TS
        for match in re.finditer(r'(?:function|const|let|var)\s+(\w+)', content):
            symbols.append(match.group(1))
        # Rust
        for match in re.finditer(r'(?:fn|struct|enum|trait)\s+(\w+)', content):
            symbols.append(match.group(1))
        # Go
        for match in re.finditer(r'func\s+(?:\([^)]*\)\s+)?(\w+)', content):
            symbols.append(match.group(1))
        
        return list(set(symbols))
    
    def _truncate_snippet(self, snippet: CodeSnippet, max_tokens: int) -> CodeSnippet | None:
        """Truncate snippet to fit token budget."""
        if self._estimate_tokens(snippet.content) <= max_tokens:
            return snippet
        
        # Try to truncate from the middle
        lines = snippet.content.splitlines()
        if len(lines) <= 3:
            return None
        
        # Keep first and last few lines
        keep_start = lines[:3]
        keep_end = lines[-3:]
        truncated = "\n".join(keep_start + ["... (truncated) ..."] + keep_end)
        
        if self._estimate_tokens(truncated) <= max_tokens:
            return CodeSnippet(
                file_path=snippet.file_path,
                start_line=snippet.start_line,
                end_line=snippet.end_line,
                content=truncated,
                relevance_score=snippet.relevance_score * 0.8,
                snippet_type=snippet.snippet_type,
                symbols=snippet.symbols,
                language=snippet.language,
            )
        return None
    
    def _detect_language(self, file_path: str) -> str:
        """Detect programming language from file extension."""
        ext = Path(file_path).suffix.lower()
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".jsx": "javascript",
            ".ts": "typescript",
            ".tsx": "typescript",
            ".rs": "rust",
            ".go": "go",
            ".java": "java",
            ".cpp": "cpp",
            ".cc": "cpp",
            ".cxx": "cpp",
            ".c": "c",
            ".h": "c",
            ".hpp": "cpp",
            ".cs": "csharp",
            ".rb": "ruby",
            ".php": "php",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".r": "r",
            ".jl": "julia",
            ".lua": "lua",
            ".sh": "bash",
            ".bash": "bash",
            ".zsh": "bash",
            ".fish": "fish",
            ".ps1": "powershell",
            ".sql": "sql",
            ".html": "html",
            ".htm": "html",
            ".css": "css",
            ".scss": "scss",
            ".sass": "sass",
            ".less": "less",
            ".json": "json",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".toml": "toml",
            ".ini": "ini",
            ".cfg": "ini",
            ".conf": "ini",
            ".xml": "xml",
            ".md": "markdown",
            ".txt": "text",
        }
        return lang_map.get(ext, "unknown")


class ContextEfficiencyManager:
    """Manages context efficiency with map-reduce pruning and KV cache."""
    
    def __init__(
        self,
        config: Config,
        workspace: Workspace,
        policy: Policy,
    ):
        self.config = config
        self.workspace = workspace
        self.policy = policy
        
        self.indexer = CodebaseIndexer(workspace, policy)
        self.pruner = ContextPruner(workspace, policy, self.indexer, config.max_context_tokens)
        self.max_context_tokens = config.max_context_tokens
    
    async def initialize(self):
        """Initialize the context efficiency manager."""
        await self.indexer.index_workspace()
    
    async def get_relevant_context(
        self,
        query: str,
        current_files: list[str] | None = None,
        max_tokens: int | None = None,
    ) -> list[CodeSnippet]:
        """Get relevant context snippets for a query."""
        return await self.pruner.prune_context(query, current_files, max_tokens)
    
    def build_context_string(self, snippets: list[CodeSnippet]) -> str:
        """Build a context string from snippets."""
        if not snippets:
            return ""
        
        parts = []
        for snippet in snippets:
            header = f"# {snippet.file_path}:{snippet.start_line}-{snippet.end_line} ({snippet.snippet_type})"
            if snippet.symbols:
                header += f" [symbols: {', '.join(snippet.symbols[:5])}]"
            parts.append(f"{header}\n```{snippet.language}\n{snippet.content}\n```")
        
        return "\n\n".join(parts)
    
    def get_index_stats(self) -> dict:
        """Get indexing statistics."""
        return {
            "total_files": self.indexer.codebase_map.total_files,
            "total_lines": self.indexer.codebase_map.total_lines,
            "total_symbols": len(self.indexer.codebase_map.symbols),
            "total_imports": len(self.indexer.codebase_map.imports),
            "last_updated": self.indexer.codebase_map.last_updated,
        }