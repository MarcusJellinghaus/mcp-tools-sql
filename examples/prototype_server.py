"""Prototype MCP server with dynamically-registered tools.

Spike Level 3: run this as a real MCP server and connect from Claude Code
to verify that dynamically-created tools are discoverable and callable.

Setup — add to your Claude Code MCP config (.mcp.json or settings):

    {
      "mcpServers": {
        "sql-prototype": {
          "command": "uv",
          "args": ["run", "--directory", "<path-to-mcp-tools-sql>",
                   "python", "examples/prototype_server.py"]
        }
      }
    }

Then start a new Claude Code session. You should see three tools:
  - query_customers_by_country
  - query_orders
  - update_order_status
"""

from __future__ import annotations

import inspect
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from mcp_tools_sql.utils.data_type_utility.type_mapping import resolve_python_type

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

CUSTOMERS = [
    {"id": 1, "name": "Bank A", "country": "Germany"},
    {"id": 2, "name": "Bank B", "country": "France"},
    {"id": 3, "name": "Bank C", "country": "Germany"},
    {"id": 4, "name": "Insurance D", "country": "Spain"},
]

ORDERS = [
    {"id": 1, "customer_id": 1, "status": "pending", "total": 1000.0},
    {"id": 2, "customer_id": 1, "status": "shipped", "total": 2500.0},
    {"id": 3, "customer_id": 2, "status": "pending", "total": 750.0},
    {"id": 4, "customer_id": 3, "status": "delivered", "total": 3200.0},
    {"id": 5, "customer_id": 4, "status": "pending", "total": 500.0},
]


# ---------------------------------------------------------------------------
# Dynamic tool builder (same pattern as tests)
# ---------------------------------------------------------------------------


def _make_tool(
    name: str,
    description: str,
    params: list[dict[str, object]],
    handler: object,
) -> None:
    """Build a dynamic tool function and register it on the MCP server."""
    async def _tool_fn(**kwargs: object) -> str:  # type: ignore[misc]
        return handler(**kwargs)  # type: ignore[operator]

    sig_params: list[inspect.Parameter] = []
    for p in params:
        python_type = resolve_python_type(str(p["type"]))
        required = bool(p.get("required", True))
        desc = str(p.get("description", ""))

        if required:
            ann: object = (
                Annotated[python_type, Field(description=desc)] if desc else python_type
            )
            default: object = inspect.Parameter.empty
        else:
            ann = (
                Annotated[Optional[python_type], Field(description=desc)]
                if desc
                else Optional[python_type]
            )
            default = None

        sig_params.append(
            inspect.Parameter(
                str(p["name"]),
                kind=inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=default,
                annotation=ann,
            )
        )

    _tool_fn.__signature__ = inspect.Signature(sig_params)  # type: ignore[attr-defined]
    _tool_fn.__name__ = name
    _tool_fn.__doc__ = description
    mcp.add_tool(_tool_fn)


# ---------------------------------------------------------------------------
# Mock handlers
# ---------------------------------------------------------------------------


def _handle_query_customers_by_country(**kwargs: object) -> str:
    country = str(kwargs.get("country", ""))
    rows = [c for c in CUSTOMERS if c["country"].lower() == country.lower()]
    if not rows:
        return f"No customers found in '{country}'."
    lines = [f"| {r['id']} | {r['name']} | {r['country']} |" for r in rows]
    header = "| id | name | country |\n|---|---|---|"
    return f"Found {len(rows)} customer(s):\n{header}\n" + "\n".join(lines)


def _handle_query_orders(**kwargs: object) -> str:
    rows = list(ORDERS)
    status = kwargs.get("status")
    if status:
        rows = [o for o in rows if o["status"] == status]
    min_total = kwargs.get("min_total")
    if min_total is not None:
        rows = [o for o in rows if o["total"] >= float(str(min_total))]
    if not rows:
        return "No orders match the given criteria."
    lines = [
        f"| {r['id']} | {r['customer_id']} | {r['status']} | {r['total']:.2f} |"
        for r in rows
    ]
    header = "| id | customer_id | status | total |\n|---|---|---|---|"
    return f"Found {len(rows)} order(s):\n{header}\n" + "\n".join(lines)


def _handle_update_order_status(**kwargs: object) -> str:
    order_id = int(str(kwargs["order_id"]))
    new_status = str(kwargs["status"])
    notes = kwargs.get("notes", "")
    for order in ORDERS:
        if order["id"] == order_id:
            old = order["status"]
            order["status"] = new_status
            msg = f"Order {order_id}: status changed '{old}' -> '{new_status}'."
            if notes:
                msg += f" Notes: {notes}"
            return msg
    return f"Order {order_id} not found."


# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

mcp = FastMCP("sql-prototype")

_make_tool(
    name="query_customers_by_country",
    description="Find customers in a specific country.",
    params=[
        {
            "name": "country",
            "type": "str",
            "description": "Country name to filter by (e.g. 'Germany', 'France')",
        },
    ],
    handler=_handle_query_customers_by_country,
)

_make_tool(
    name="query_orders",
    description="Search orders with optional filters.",
    params=[
        {
            "name": "status",
            "type": "str",
            "description": "Filter by order status (pending, shipped, delivered)",
            "required": False,
        },
        {
            "name": "min_total",
            "type": "float",
            "description": "Minimum order total",
            "required": False,
        },
    ],
    handler=_handle_query_orders,
)

_make_tool(
    name="update_order_status",
    description="Update the status of an order by its ID.",
    params=[
        {
            "name": "order_id",
            "type": "int",
            "description": "The order ID to update",
        },
        {
            "name": "status",
            "type": "str",
            "description": "New status value (pending, shipped, delivered)",
        },
        {
            "name": "notes",
            "type": "str",
            "description": "Optional notes about the status change",
            "required": False,
        },
    ],
    handler=_handle_update_order_status,
)

if __name__ == "__main__":
    mcp.run("stdio")
