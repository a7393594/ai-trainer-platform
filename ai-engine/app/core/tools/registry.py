"""
Tool Registry -- Register, manage, and execute external tools
"""
import time
import httpx
from app.db import crud


class ToolRegistry:

    async def register_tool(self, tenant_id: str, name: str, description: str,
                            tool_type: str, config_json: dict,
                            auth_config: dict = None, permissions: list = None,
                            rate_limit: str = None) -> dict:
        return crud.create_tool(
            tenant_id=tenant_id,
            name=name,
            description=description,
            tool_type=tool_type,
            config_json=config_json,
            auth_config=auth_config or {},
            permissions=permissions or ["admin", "trainer"],
            rate_limit=rate_limit,
        )

    async def execute_tool(self, tool_id: str, params: dict = None,
                           dry_run: bool = False, tenant_id: str = None,
                           user_id: str = None) -> dict:
        tool = crud.get_tool(tool_id)
        if not tool:
            return {"status": "error", "detail": "Tool not found"}
        if not tool.get("is_active"):
            return {"status": "error", "detail": "Tool is inactive"}

        start = time.time()
        result = {}

        try:
            if dry_run:
                result = {"status": "dry_run", "tool": tool["name"], "params": params}
            elif tool["tool_type"] == "api_call":
                result = await self._execute_api_call(tool, params or {})
            elif tool["tool_type"] == "webhook":
                result = await self._execute_webhook(tool, params or {})
            else:
                result = {"status": "error", "detail": f"Unsupported type: {tool['tool_type']}"}
        except Exception as e:
            result = {"status": "error", "detail": str(e)}

        duration = int((time.time() - start) * 1000)

        # Log
        if tenant_id:
            crud.create_audit_log(
                tenant_id=tenant_id,
                user_id=user_id,
                action_type="tool_call",
                tool_id=tool_id,
                request_data=params,
                response_data=result,
                status="dry_run" if dry_run else ("success" if result.get("status") != "error" else "error"),
                duration_ms=duration,
            )

        return result

    async def _execute_api_call(self, tool: dict, params: dict) -> dict:
        config = tool.get("config_json", {})
        method = config.get("method", "GET").upper()
        url = config.get("url", "")
        headers = config.get("headers", {})

        # Template URL params
        for key, val in params.items():
            url = url.replace(f"{{{key}}}", str(val))

        async with httpx.AsyncClient(timeout=30) as client:
            if method == "GET":
                r = await client.get(url, headers=headers, params=params)
            else:
                r = await client.request(method, url, headers=headers, json=params)

            return {"status": "success", "status_code": r.status_code, "data": r.text[:2000]}

    async def _execute_webhook(self, tool: dict, params: dict) -> dict:
        config = tool.get("config_json", {})
        url = config.get("url", "")

        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=params)
            return {"status": "success", "status_code": r.status_code}

    async def list_tools(self, tenant_id: str) -> list[dict]:
        return crud.list_tools(tenant_id)

    async def test_tool(self, tool_id: str, tenant_id: str = None) -> dict:
        return await self.execute_tool(tool_id, params={"test": True}, dry_run=True, tenant_id=tenant_id)


tool_registry = ToolRegistry()
