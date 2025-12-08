#!/usr/bin/env python3
"""Customer service agent with full observability.

Lab 3.5 Deliverable: Demonstrates structured logging, debug webhooks,
post-prompt handling, health endpoints, and monitoring patterns.
"""

import os
import json
import time
import logging
from datetime import datetime
from signalwire_agents import AgentBase, AgentServer, SwaigFunctionResult


# ============================================================
# Structured Logging Setup
# ============================================================

class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record):
        log_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName
        }

        extra_fields = [
            "call_id", "customer_id", "function_name",
            "duration_ms", "error_type", "ticket_id",
            "priority", "department"
        ]
        for key in extra_fields:
            if hasattr(record, key):
                log_data[key] = getattr(record, key)

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging():
    """Configure structured JSON logging."""
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())

    logger = logging.getLogger("agent")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    return logger


# ============================================================
# Observable Agent
# ============================================================

class ObservableAgent(AgentBase):
    """Customer service agent with comprehensive observability."""

    def __init__(self):
        super().__init__(name="observable-agent")

        self.logger = setup_logging()
        self.logger.info("Agent initializing")

        self._configure_prompts()
        self._configure_monitoring()
        self.add_language("English", "en-US", "rime.spore")
        self._setup_functions()

        self.logger.info("Agent initialized successfully")

    def _configure_prompts(self):
        """Configure agent prompts."""
        self.prompt_add_section(
            "Role",
            "Customer service agent. Help with orders and support."
        )

        self.prompt_add_section(
            "Guidelines",
            bullets=[
                "Be helpful and efficient",
                "Create tickets for complex issues",
                "Transfer to specialists when needed"
            ]
        )

    def _configure_monitoring(self):
        """Configure debug webhooks and post-prompt for observability."""
        # Get base URL for webhooks
        base_url = self.get_full_url().rstrip('/')

        # Debug webhook for real-time monitoring
        self.set_params({
            "debug_webhook_url": f"{base_url}/debug",
            "debug_webhook_level": 1
        })

        # Post-prompt for call summarization
        self.set_post_prompt("""
            Summarize this customer interaction as JSON:
            {
                "outcome": "resolved|escalated|pending",
                "topics_discussed": [],
                "action_items": [],
                "customer_sentiment": "positive|neutral|negative",
                "ticket_created": true/false
            }
        """)
        self.set_post_prompt_url(f"{base_url}/post_prompt")

    def _log_function_call(
        self,
        func_name: str,
        call_id: str,
        duration_ms: float,
        success: bool,
        error: str = None
    ):
        """Log function execution with context."""
        extra = {
            "call_id": call_id,
            "function_name": func_name,
            "duration_ms": round(duration_ms, 2)
        }

        if success:
            self.logger.info(f"Function {func_name} completed", extra=extra)
        else:
            extra["error_type"] = error
            self.logger.error(f"Function {func_name} failed: {error}", extra=extra)

    def _setup_functions(self):
        """Define observable functions."""

        @self.tool(
            description="Look up order status",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Order ID to look up"
                    }
                },
                "required": ["order_id"]
            },
            fillers=["Looking up your order..."]
        )
        def get_order_status(args: dict, raw_data: dict = None) -> SwaigFunctionResult:
            raw_data = raw_data or {}
            order_id = args.get("order_id", "unknown")
            call_id = raw_data.get("call_id", "unknown")
            start = time.perf_counter()

            try:
                # Simulated order lookup
                time.sleep(0.2)
                status = "shipped"
                duration_ms = (time.perf_counter() - start) * 1000

                self._log_function_call(
                    "get_order_status",
                    call_id,
                    duration_ms,
                    success=True
                )

                return SwaigFunctionResult(f"Order {order_id}: {status}")

            except Exception as e:
                duration_ms = (time.perf_counter() - start) * 1000
                self._log_function_call(
                    "get_order_status",
                    call_id,
                    duration_ms,
                    success=False,
                    error=str(e)
                )
                return SwaigFunctionResult(
                    "I'm having trouble looking up that order. "
                    "Can I help with something else?"
                )

        @self.tool(
            description="Create a support ticket",
            parameters={
                "type": "object",
                "properties": {
                    "issue": {
                        "type": "string",
                        "description": "Description of the issue"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Ticket priority"
                    }
                },
                "required": ["issue"]
            }
        )
        def create_ticket(args: dict, raw_data: dict = None) -> SwaigFunctionResult:
            raw_data = raw_data or {}
            issue = args.get("issue", "")
            priority = args.get("priority", "medium")
            call_id = raw_data.get("call_id", "unknown")
            start = time.perf_counter()

            ticket_id = f"TKT-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            duration_ms = (time.perf_counter() - start) * 1000

            self._log_function_call(
                "create_ticket",
                call_id,
                duration_ms,
                success=True
            )

            # Log business event
            self.logger.info(
                "Ticket created",
                extra={
                    "call_id": call_id,
                    "ticket_id": ticket_id,
                    "priority": priority
                }
            )

            return (
                SwaigFunctionResult(f"Created ticket {ticket_id}.")
                .update_global_data({
                    "ticket_id": ticket_id,
                    "ticket_priority": priority
                })
            )

        @self.tool(
            description="Transfer to specialist",
            parameters={
                "type": "object",
                "properties": {
                    "department": {
                        "type": "string",
                        "enum": ["sales", "support", "billing"],
                        "description": "Department to transfer to"
                    }
                },
                "required": ["department"]
            }
        )
        def transfer_specialist(args: dict, raw_data: dict = None) -> SwaigFunctionResult:
            raw_data = raw_data or {}
            department = args.get("department", "support")
            call_id = raw_data.get("call_id", "unknown")

            self.logger.info(
                "Transfer initiated",
                extra={
                    "call_id": call_id,
                    "department": department
                }
            )

            return (
                SwaigFunctionResult(f"Transferring to {department}.", post_process=True)
                .swml_transfer(f"/agents/{department}", "Goodbye!", final=True)
            )

        @self.tool(description="Get system status")
        def system_status(args: dict, raw_data: dict = None) -> SwaigFunctionResult:
            return SwaigFunctionResult("All systems operational.")


# ============================================================
# Server with Health Endpoints
# ============================================================

def create_server():
    """Create server with health and monitoring endpoints."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))

    server = AgentServer(host=host, port=port)
    agent = ObservableAgent()
    server.register(agent)

    # Health endpoint
    @server.app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": os.getenv("APP_VERSION", "1.0.0")
        }

    # Readiness endpoint
    @server.app.get("/ready")
    async def ready():
        return {"ready": True}

    # Debug webhook endpoint
    @server.app.post("/debug")
    async def debug_webhook(request):
        """Receive debug data from SignalWire."""
        data = await request.json()
        logging.getLogger("agent").info(
            "Debug webhook received",
            extra={"debug_data": json.dumps(data)[:500]}
        )
        return {"received": True}

    # Post-prompt webhook endpoint
    @server.app.post("/post_prompt")
    async def post_prompt_webhook(request):
        """Receive post-prompt summary data."""
        data = await request.json()
        logging.getLogger("agent").info(
            "Post-prompt received",
            extra={"summary": json.dumps(data)[:500]}
        )
        return {"received": True}

    return server


if __name__ == "__main__":
    server = create_server()
    server.run()
