# Model Context Protocol (MCP) Configuration Guide

## Overview

The `.mcp.json` file in the repository root configures Model Context Protocol (MCP) servers for
VS Code Copilot integration. MCP allows Copilot to interact with external tools and services.

## Configuration File

- **Location**: `.mcp.json` (root directory, gitignored)
- **Example**: `.mcp.json.example` (template with documentation)

## Docker MCP Gateway Issue (Fixed)

### Problem

Prior to this fix, the repository included a Docker MCP gateway configuration that caused errors:

```text
Invalid schema for function 'mcp_mcp_docker_mcp-config-set':
In context=('properties', 'value', 'type', '4'), array schema missing items.
```

### Root Cause

1. Docker version 29.1.5 (and earlier) does not include the `docker mcp gateway run` command
2. The Docker MCP gateway feature requires Docker Desktop with MCP support
3. Even with MCP support, the gateway had schema validation issues with array type definitions

### Solution

The Docker MCP configuration has been removed from `.mcp.json` to prevent this error. If you need
Docker MCP integration and have a compatible Docker Desktop version, you can re-enable it by:

1. Verifying Docker MCP support:

   ```bash
   docker mcp --help
   ```

2. If available, add to `.mcp.json`:

   ```json
   {
     "mcpServers": {
       "MCP_DOCKER": {
         "command": "docker",
         "args": ["mcp", "gateway", "run"],
         "env": {
           "LOCALAPPDATA": "%LOCALAPPDATA%",
           "ProgramData": "C:\\ProgramData",
           "ProgramFiles": "C:\\Program Files"
         },
         "type": "stdio"
       }
     }
   }
   ```

## Adding Custom MCP Servers

To add your own MCP servers:

1. Copy `.mcp.json.example` to `.mcp.json` (if not already present)
2. Add server configurations following this pattern:

   ```json
   {
     "mcpServers": {
       "YOUR_SERVER_NAME": {
         "command": "path/to/executable",
         "args": ["arg1", "arg2"],
         "env": {
           "ENV_VAR": "value"
         },
         "type": "stdio"
       }
     }
   }
   ```

## References

- [Model Context Protocol Documentation](https://modelcontextprotocol.io/)
- [Docker Desktop MCP Integration](https://docs.docker.com/) (when available)
- PR: #346 - Docker MCP schema error fix

## Version History

- **2026-02-14**: Removed Docker MCP configuration due to compatibility issues
- Initial configuration with Docker MCP gateway
