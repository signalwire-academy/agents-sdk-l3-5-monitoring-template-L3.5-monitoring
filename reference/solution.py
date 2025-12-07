#!/usr/bin/env python3
"""Customer service agent with full observability.

Lab 3.5 Deliverable: Demonstrates structured logging, Prometheus metrics,
health endpoints, and comprehensive monitoring patterns.
"""

import os
import json
import time
import logging
from datetime import datetime
from signalwire_agents import AgentBase, AgentServer, SwaigFunctionResult

# Try to import prometheus_client, but don't fail if not available
try:
    from prometheus_client import Counter, Histogram, Gauge, start_http_server
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


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

        # Add extra fields if present
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
# Prometheus Metrics (if available)
# ============================================================

if PROMETHEUS_AVAILABLE:
    # Call metrics
    CALLS_TOTAL = Counter(
        'voice_agent_calls_total',
        'Total calls received',
        ['agent', 'status']
    )

    ACTIVE_CALLS = Gauge(
        'voice_agent_active_calls',
        'Currently active calls',
        ['agent']
    )

    # Function metrics
    FUNCTION_CALLS = Counter(
        'voice_agent_function_calls_total',
        'Total function calls',
        ['agent', 'function', 'status']
    )

    FUNCTION_LATENCY = Histogram(
        'voice_agent_function_latency_seconds',
        'Function execution latency',
        ['agent', 'function'],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    )

    # Business metrics
    TICKETS_CREATED = Counter(
        'voice_agent_tickets_total',
        'Support tickets created',
        ['agent', 'priority']
    )

    TRANSFERS_TOTAL = Counter(
        'voice_agent_transfers_total',
        'Call transfers',
        ['agent', 'department']
    )

    # Error metrics
    ERRORS_TOTAL = Counter(
        'voice_agent_errors_total',
        'Total errors',
        ['agent', 'function', 'error_type']
    )


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

    def _log_function_call(
        self,
        func_name: str,
        call_id: str,
        duration_ms: float,
        success: bool,
        error: str = None
    ):
        """Log function execution with context and metrics."""
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

        # Update Prometheus metrics if available
        if PROMETHEUS_AVAILABLE:
            status = "success" if success else "error"

            FUNCTION_CALLS.labels(
                agent="observable-agent",
                function=func_name,
                status=status
            ).inc()

            FUNCTION_LATENCY.labels(
                agent="observable-agent",
                function=func_name
            ).observe(duration_ms / 1000)

            if not success:
                ERRORS_TOTAL.labels(
                    agent="observable-agent",
                    function=func_name,
                    error_type=error or "unknown"
                ).inc()

    def _setup_functions(self):
        """Define observable functions."""

        @self.tool(
            description="Look up order status",
            parameters={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"}
                },
                "required": ["order_id"]
            },
            fillers=["Looking up your order..."]
        )
        def get_order_status(order_id: str, raw_data: dict) -> SwaigFunctionResult:
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
                    "issue": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high"]
                    }
                },
                "required": ["issue"]
            }
        )
        def create_ticket(
            issue: str,
            priority: str = "medium",
            raw_data: dict = None
        ) -> SwaigFunctionResult:
            call_id = raw_data.get("call_id", "unknown") if raw_data else "unknown"
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

            # Update business metrics
            if PROMETHEUS_AVAILABLE:
                TICKETS_CREATED.labels(
                    agent="observable-agent",
                    priority=priority
                ).inc()

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
                        "enum": ["sales", "support", "billing"]
                    }
                },
                "required": ["department"]
            }
        )
        def transfer_specialist(
            department: str,
            raw_data: dict
        ) -> SwaigFunctionResult:
            call_id = raw_data.get("call_id", "unknown")

            self.logger.info(
                "Transfer initiated",
                extra={
                    "call_id": call_id,
                    "department": department
                }
            )

            # Update business metrics
            if PROMETHEUS_AVAILABLE:
                TRANSFERS_TOTAL.labels(
                    agent="observable-agent",
                    department=department
                ).inc()

            return (
                SwaigFunctionResult(f"Transferring to {department}.", post_process=True)
                .swml_transfer(f"/agents/{department}", "Goodbye!", final=True)
            )

        @self.tool(description="Get system status")
        def system_status() -> SwaigFunctionResult:
            return SwaigFunctionResult("All systems operational.")


# ============================================================
# Server with Health Endpoints
# ============================================================

def create_server():
    """Create server with health and metrics endpoints."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "3000"))
    metrics_port = int(os.getenv("METRICS_PORT", "9090"))

    server = AgentServer(host=host, port=port)
    agent = ObservableAgent()
    server.register(agent)

    # Start Prometheus metrics server if available
    if PROMETHEUS_AVAILABLE:
        try:
            start_http_server(metrics_port)
            print(f"Metrics server started on port {metrics_port}")
        except Exception as e:
            print(f"Could not start metrics server: {e}")

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

    # Detailed health check
    @server.app.get("/health/detailed")
    async def health_detailed():
        checks = {
            "agent": {"status": "healthy"},
            "metrics": {"status": "healthy" if PROMETHEUS_AVAILABLE else "unavailable"}
        }

        try:
            # Test SWML generation
            agent.get_swml()
            checks["swml_generation"] = {"status": "healthy"}
        except Exception as e:
            checks["swml_generation"] = {"status": "unhealthy", "error": str(e)}

        all_healthy = all(
            c.get("status") == "healthy"
            for c in checks.values()
            if isinstance(c, dict) and c.get("status") != "unavailable"
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks
        }

    # Metrics info endpoint
    @server.app.get("/metrics/info")
    async def metrics_info():
        return {
            "metrics_available": PROMETHEUS_AVAILABLE,
            "metrics_port": metrics_port if PROMETHEUS_AVAILABLE else None,
            "available_metrics": [
                "voice_agent_calls_total",
                "voice_agent_function_calls_total",
                "voice_agent_function_latency_seconds",
                "voice_agent_tickets_total",
                "voice_agent_transfers_total",
                "voice_agent_errors_total"
            ] if PROMETHEUS_AVAILABLE else []
        }

    return server


if __name__ == "__main__":
    server = create_server()
    server.run()
