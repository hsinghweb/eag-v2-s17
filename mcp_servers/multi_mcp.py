
import asyncio
import sys
import shutil
import json
import os
from pathlib import Path
from contextlib import AsyncExitStack
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool
from rich import print

class MultiMCP:
    def __init__(self):
        self.exit_stack = AsyncExitStack()
        self.sessions = {}  # server_name -> session
        self.tools = {}     # server_name -> [Tool]
        
        # Robust path resolution
        self.base_dir = Path(__file__).parent
        self.config_path = self.base_dir / "mcp_config.json"
        
        # Metadata Cache (for tools)
        self.cache_path = self.base_dir.parent / "config" / "mcp_cache.json"
        self._cached_metadata = self._load_cache()
        
        self.server_configs = self._load_config()
        
        # Disabled tools cache
        self.disabled_tools = set() # { "server:tool" }
        self.disabled_tools_path = self.base_dir.parent / "config" / "disabled_tools.json"
        self._load_disabled_tools()

    def _load_config(self) -> dict:
        """Load server configuration from JSON"""
        if self.config_path.exists():
            try:
                return json.loads(self.config_path.read_text())
            except Exception as e:
                print(f"⚠️ Failed to load MCP config: {e}")
        return {}

    def _save_config(self):
        """Save current server configuration"""
        try:
            self.config_path.write_text(json.dumps(self.server_configs, indent=2))
        except Exception as e:
            print(f"⚠️ Failed to save MCP config: {e}")

    def _load_disabled_tools(self):
        if self.disabled_tools_path.exists():
            try:
                data = json.loads(self.disabled_tools_path.read_text())
                self.disabled_tools = set(data)
            except: pass

    def _save_disabled_tools(self):
        self.disabled_tools_path.write_text(json.dumps(list(self.disabled_tools)))
        
    def set_tool_state(self, server_name: str, tool_name: str, enabled: bool):
        key = f"{server_name}:{tool_name}"
        if enabled:
            if key in self.disabled_tools:
                self.disabled_tools.remove(key)
                self._save_disabled_tools()
        else:
            self.disabled_tools.add(key)
            self._save_disabled_tools()

    async def add_server(self, name: str, config: dict):
        """Dynamically add a new server"""
        if name in self.sessions:
            raise ValueError(f"Server '{name}' already exists")
        
        self.server_configs[name] = config
        self._save_config()
        
        # Start immediately
        await self._start_server(name, config)
        return True

    async def remove_server(self, name: str):
        """Remove a server"""
        try:
            if name in self.server_configs:
                del self.server_configs[name]
                self._save_config()
            
            # Remove from active sessions/tools regardless of config presence
            if name in self.sessions:
                # We can't strictly 'close' the session easily without closing the whole stack
                # unless we manage per-session exit stacks (which would be better but complex refactor)
                # For now, just removing it prevents further routing.
                print(f"  🗑️ Removed server '{name}' from sessions")
                del self.sessions[name]
                
            if name in self.tools:
                del self.tools[name]
                
            return True
        except Exception as e:
            print(f"  ⚠️ Error removing server {name}: {e}")
            # Still return True if we managed to at least remove it from config? 
            # Or False? Let's return True effectively as "we tried our best to forget it"
            return True

    async def _start_server(self, name: str, config: dict):
        """Start a single server with timeout protection"""
        # Skip if explicitly disabled
        if config.get("enabled", True) is False:
            print(f"  ⏭️ [dim]Server '{name}' is disabled in config. Skipping.[/dim]")
            return False

        try:
            cmd = config.get("command", "uv")
            args = config.get("args", [])
            server_type = config.get("type", "local-script")
            env = config.get("env", None) # Optional env vars
            server_cwd = None
            final_env = os.environ.copy()
            if env:
                final_env.update(env)

            # --- Pre-processing for different types ---
            
            if server_type == "local-script":
                # Ensure we point to the script in this directory
                script_name = args[-1] # Assume last arg is script
                if not Path(script_name).is_absolute() and (self.base_dir / script_name).exists():
                     # Reconstruct args with absolute path
                     # args usually: ["run", "server_browser.py"]
                     script_path = str(self.base_dir / script_name)
                     args = args[:-1] + [script_path]
                server_cwd = self.base_dir

            elif server_type == "stdio-git":
                # Clone repo and setup
                repo_url = config.get("source")
                if not repo_url:
                    raise ValueError("Missing 'source' (git url) for stdio-git server")
                
                server_dir = self.base_dir.parent / "data" / "mcp_repos" / name
                server_dir.parent.mkdir(parents=True, exist_ok=True)
                server_cwd = server_dir
                
                if not server_dir.exists():
                     print(f"  ⬇️ Cloning {name} from {repo_url}...")
                     proc = await asyncio.create_subprocess_exec(
                         "git", "clone", repo_url, str(server_dir),
                         stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                     )
                     await proc.communicate()
                     if proc.returncode != 0:
                         raise RuntimeError(f"Git clone failed for {name}")


                # Configure command to run from that directory with uv
                # We typically run `uv run --directory <repo> <script>`
                cmd = "uv"
                
                if cmd == "uv" and "run" in args:
                     # Inject --directory <path> after 'run' 
                     # args is likely ["run", "script.py"]
                     # We want ["run", "--directory", str(server_dir), "script.py"]
                     
                     # Find index of 'run'
                     try:
                         run_idx = args.index("run")
                         # Insert directory args after run
                         args.insert(run_idx + 1, "--directory")
                         args.insert(run_idx + 2, str(server_dir))
                         
                         # Check for requirements.txt to install dependencies automatically
                         req_file = server_dir / "requirements.txt"
                         if req_file.exists():
                             args.insert(run_idx + 3, "--with-requirements")
                             args.insert(run_idx + 4, str(req_file))
                             print(f"  📦 Detected requirements.txt for {name}, auto-installing dependencies...")
                         
                         # --- Smart Entry Point Detection ---
                         # The config might default to 'src/server.py', but the repo might use 'yfinance_mcp_server.py'
                         # We check the LAST argument which is usually the script path
                         script_arg_idx = -1
                         current_script = args[script_arg_idx]
                         
                         # Construct full path to check
                         script_path = server_dir / current_script
                         if not script_path.exists():
                             print(f"  ⚠️ Configured script '{current_script}' not found in {name}. Attempting auto-detection...")
                             
                             # Search candidates
                             candidates = list(server_dir.glob("*_mcp_server.py")) + \
                                          list(server_dir.glob("server.py")) + \
                                          list(server_dir.glob("src/server.py")) + \
                                          list(server_dir.glob("*.py"))
                             
                             # Filter out non-server looking files if possible, but taking the first specific match is good
                             best_candidate = None
                             for c in candidates:
                                 # Prefer *mcp_server.py or server.py
                                 if "mcp_server" in c.name or c.name == "server.py":
                                     best_candidate = c
                                     break
                             
                             if not best_candidate and candidates:
                                 # Fallback to first python file if it looks like a server?
                                 # Just take the first one (often there's only one main script in simple repos)
                                 best_candidate = candidates[0]
                             
                             if best_candidate:
                                 # Update args
                                 new_script = str(best_candidate.relative_to(server_dir))
                                 args[script_arg_idx] = new_script
                                 print(f"  ✅ Auto-detected entry point: {new_script}")
                             else:
                                 print(f"  ❌ Could not auto-detect entry point for {name}")

                     except ValueError:
                         pass
            
            # --- Execution ---

            # Check if uv exists fallback
            if cmd == "uv" and not shutil.which("uv"):
                cmd = sys.executable
                # This fallback is flaky for complex args, keep simple
                if args[0] == "run":
                     # If falling back to python, we need to handle the directory/cwd manually
                     # or just hope it works?
                     # Ideally we shouldn't fallback for git repos if they rely on uv dependencies
                     print(f"  ⚠️ 'uv' not found. Falling back to system python is risky for {name}.")
                     # Try to fix path to be absolute if we are not using uv (and not changing cwd)
                     # But we can't easily change cwd for just this process with StdioServerParameters efficiently?
                     # Actually we can just run python <full_path_to_script>
                     # Remove 'run', '--directory', etc.
                     # This is Getting Complicated. Let's assume UV exists for 'stdio-git'.
                     pass # Rely on uv being present


            server_params = StdioServerParameters(
                command=cmd,
                args=args,
                env=final_env
            )
            
            # Connect with timeout
            async with asyncio.timeout(20): # 20s timeout (increased for installations)
                read, write = await self.exit_stack.enter_async_context(stdio_client(server_params))
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                
                # List tools
                if name in self._cached_metadata:
                    print(f"  📦 [cyan]{name}[/cyan] tools loaded from cache.")
                    cached_tools = []
                    for t_dict in self._cached_metadata[name]:
                        cached_tools.append(Tool(
                            name=t_dict["name"],
                            description=t_dict["description"],
                            inputSchema=t_dict["inputSchema"]
                        ))
                    self.tools[name] = cached_tools
                else:
                    result = await session.list_tools()
                    self.tools[name] = result.tools
                    self._save_to_cache(name, result.tools)
                    print(f"  ✅ [cyan]{name}[/cyan] connected. Tools: {len(result.tools)}")
                
                self.sessions[name] = session

        except NotImplementedError as e:
            print(f"  ❌ [red]{name}[/red] failed to start: {e}")
            print("  ⚠️ Windows event loop does not support subprocesses. Use ProactorEventLoopPolicy.")
            return False
        except TimeoutError:
             print(f"  ⏳ [yellow]{name}[/yellow] timed out during startup.")
        except Exception as e:
            print(f"  ❌ [red]{name}[/red] failed to start: {e}")
            await self._probe_server_process(
                name=name,
                cmd=cmd,
                args=args,
                env=final_env,
                cwd=server_cwd,
            )
        except BaseException as e:
            print(f"  ❌ [red]{name}[/red] CRITICAL FAILURE: {e}")

    async def _probe_server_process(
        self,
        name: str,
        cmd: str,
        args: list,
        env: dict = None,
        cwd: Path = None,
        timeout: float = 8.0,
    ):
        """Run the server command briefly to capture stdout/stderr for diagnostics."""
        try:
            cmd_display = " ".join([cmd] + args)
            cwd_display = str(cwd) if cwd else "<default>"
            print(f"  🔎 Probing [cyan]{name}[/cyan] server process for errors...")
            print(f"  🔧 Command: {cmd_display}")
            print(f"  📁 CWD: {cwd_display}")

            proc = await asyncio.create_subprocess_exec(
                cmd,
                *args,
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            except asyncio.TimeoutError:
                proc.terminate()
                try:
                    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=3.0)
                except asyncio.TimeoutError:
                    proc.kill()
                    stdout, stderr = await proc.communicate()

            stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
            stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

            if stdout_text.strip():
                print(f"  📤 STDOUT:\n{stdout_text}")
            if stderr_text.strip():
                print(f"  📥 STDERR:\n{stderr_text}")
            if not stdout_text.strip() and not stderr_text.strip():
                print("  ℹ️ No stdout/stderr captured during probe.")

            if proc.returncode is not None:
                print(f"  🧾 Probe exit code: {proc.returncode}")
        except NotImplementedError as probe_error:
            print(f"  ⚠️ Probe failed for {name}: {probe_error}")
            print("  ⚠️ Windows event loop does not support subprocesses. Use ProactorEventLoopPolicy.")
        except Exception as probe_error:
            print(f"  ⚠️ Probe failed for {name}: {probe_error}")

    async def start(self):
        """Start all configured servers"""
        print("[bold green]🚀 Starting MCP Servers...[/bold green]")
        for name, config in self.server_configs.items():
            if config.get("enabled", True):
                await self._start_server(name, config)
            else:
                print(f"  ⏭️ [dim]Skipping disabled server: {name}[/dim]")

    async def stop(self):
        """Stop all servers"""
        print("[bold yellow]🛑 Stopping MCP Servers...[/bold yellow]")
        await self.exit_stack.aclose()

    def get_all_tools(self) -> list:
        """Get all tools from all connected servers"""
        all_tools = []
        for tools in self.tools.values():
            all_tools.extend(tools)
        return all_tools
    
    def get_connected_servers(self) -> list:
        """Return list of connected server names"""
        return list(self.sessions.keys())

    async def function_wrapper(self, tool_name: str, *args):
        """Execute a tool using positional arguments by mapping them to schema keys"""
        # Find tool definition
        target_tool = None
        for tools in self.tools.values():
            for tool in tools:
                if tool.name == tool_name:
                    target_tool = tool
                    break
            if target_tool: break
        
        if not target_tool:
            return f"Error: Tool {tool_name} not found"

        # Map positional args to keyword args based on schema
        arguments = {}
        schema = target_tool.inputSchema
        if schema and 'properties' in schema:
            keys = list(schema['properties'].keys())
            for i, arg in enumerate(args):
                if i < len(keys):
                    arguments[keys[i]] = arg
        
        try:
            result = await self.route_tool_call(tool_name, arguments)
            # Unpack CallToolResult
            if hasattr(result, 'content') and result.content:
                return result.content[0].text
            return str(result)
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"

    def get_tools_from_servers(self, server_names: list) -> list:
        """Get flattened list of tools from requested servers"""
        all_tools = []
        for name in server_names:
            if name in self.tools:
                # Filter out disabled tools
                for tool in self.tools[name]:
                    key = f"{name}:{tool.name}"
                    if key not in self.disabled_tools:
                        all_tools.append(tool)
        return all_tools

    async def call_tool(self, server_name: str, tool_name: str, arguments: dict):
        """Call a tool on a specific server"""
        if server_name not in self.sessions:
            raise ValueError(f"Server '{server_name}' not connected")
        
        return await self.sessions[server_name].call_tool(tool_name, arguments)

    def _find_cached_tool_schema(self, tool_name: str):
        """Find tool schema from active tools or cached metadata."""
        for tools in self.tools.values():
            for tool in tools:
                if tool.name == tool_name:
                    return tool.inputSchema
        for server_name, tools in self._cached_metadata.items():
            for tool in tools:
                if tool.get("name") == tool_name:
                    return tool.get("inputSchema")
        return None

    def _find_server_for_tool(self, tool_name: str):
        """Find the server that owns a tool (using cache as fallback)."""
        for name, tools in self.tools.items():
            for tool in tools:
                if tool.name == tool_name:
                    return name
        for server_name, tools in self._cached_metadata.items():
            for tool in tools:
                if tool.get("name") == tool_name:
                    return server_name
        return None

    def _normalize_tool_arguments(self, tool_name: str, arguments):
        """Normalize tool arguments to a dict based on schema when possible."""
        if isinstance(arguments, dict):
            return arguments

        schema = self._find_cached_tool_schema(tool_name) or {}
        props = schema.get("properties") or {}
        keys = list(props.keys())

        if isinstance(arguments, (list, tuple)):
            if keys:
                mapped = {}
                for idx, arg in enumerate(arguments):
                    if idx < len(keys):
                        mapped[keys[idx]] = arg
                return mapped
            if len(arguments) == 1:
                return {"input": arguments[0]}
            return {"input": arguments}

        if isinstance(arguments, str):
            if len(keys) == 1:
                return {keys[0]: arguments}
            return {"input": arguments}

        return {"input": arguments}

    # Helper to route tool call by finding which server has it
    async def route_tool_call(self, tool_name: str, arguments: dict):
        from core.circuit_breaker import get_breaker, CircuitOpenError
        
        # Get or create circuit breaker for this tool
        breaker = get_breaker(tool_name, failure_threshold=5, recovery_timeout=60.0)
        
        # Check if circuit allows execution
        if not breaker.can_execute():
            status = breaker.get_status()
            raise CircuitOpenError(
                f"Circuit open for '{tool_name}' - service failing. "
                f"Retry in {status['time_until_retry']:.0f}s"
            )
        
        try:
            normalized_args = self._normalize_tool_arguments(tool_name, arguments)
            for name, tools in self.tools.items():
                for tool in tools:
                    if tool.name == tool_name:
                        result = await self.call_tool(name, tool_name, normalized_args)
                        breaker.record_success()
                        return result

            # Try to start the owning server if we only have cached metadata
            cached_owner = self._find_server_for_tool(tool_name)
            if cached_owner and cached_owner not in self.sessions and cached_owner in self.server_configs:
                await self._start_server(cached_owner, self.server_configs[cached_owner])
                if cached_owner in self.sessions:
                    result = await self.call_tool(cached_owner, tool_name, normalized_args)
                    breaker.record_success()
                    return result
            raise ValueError(f"Tool '{tool_name}' not found in any server")
        except CircuitOpenError:
            raise  # Re-raise circuit errors without recording failure
        except Exception as e:
            breaker.record_failure()
            raise

    def _load_cache(self) -> dict:
        """Load metadata cache from file"""
        if self.cache_path.exists():
            try:
                import json
                return json.loads(self.cache_path.read_text())
            except Exception as e:
                print(f"  ⚠️ Failed to load MCP cache: {e}")
        return {}

    def _save_to_cache(self, server_name: str, tools: list):
        """Save tool metadata to persistent cache"""
        try:
            import json
            # Ensure directory exists
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Load existing
            cache = self._load_cache()
            
            # Update
            tool_list = []
            for t in tools:
                tool_list.append({
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema
                })
            cache[server_name] = tool_list
            
            # Write back
            self.cache_path.write_text(json.dumps(cache, indent=2))
            print(f"  💾 Cached metadata for [cyan]{server_name}[/cyan]")
        except Exception as e:
            print(f"  ⚠️ Failed to save MCP cache for {server_name}: {e}")

    async def refresh_server(self, server_name: str):
        """Force refresh tool metadata for a server"""
        if server_name in self.sessions:
            print(f"  🔄 Refreshing tools for [cyan]{server_name}[/cyan]...")
            result = await self.sessions[server_name].list_tools()
            self.tools[server_name] = result.tools
            self._save_to_cache(server_name, result.tools)
            return True
        return False
        
    def get_server_readme(self, server_name: str) -> str:
        """Get the README content for a server"""
        config = self.server_configs.get(server_name)
        if not config:
            return None
            
        repo_path = None
        
        # Determine path based on type
        if config.get("type") == "stdio-git":
             repo_path = self.base_dir.parent / "data" / "mcp_repos" / server_name
        elif config.get("type") == "local-script":
             # Use the base dir
             repo_path = self.base_dir
        
        if repo_path:
            # Try potential readme names, prioritizing server-specific ones
            candidates = [
                f"README_{server_name}.md",
                f"docs/README_{server_name}.md",
                "README.md", 
                "readme.md", 
                "README.txt", 
                "README"
            ]
            
            for name in candidates:
                p = repo_path / name
                if p.exists():
                    return p.read_text(encoding="utf-8", errors="replace")
        
        return None

