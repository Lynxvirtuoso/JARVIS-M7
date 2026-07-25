import time
import threading
from core.logger import logger

import uuid

class TelemetryContext:
    def __init__(self, command: str, request_id: str | None = None):
        self.command = command
        self.request_id = request_id or uuid.uuid4().hex
        self.start_time = time.time()
        self.events = []

class PipelineTimer:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = PipelineTimer()
        return cls._instance

    def __init__(self):
        self._local = threading.local()
        self.active_playing_context = None

    def get_thread_context(self):
        return getattr(self._local, "current_context", None)

    def set_thread_context(self, ctx):
        self._local.current_context = ctx

    def reset(self):
        self._local.current_context = None
        self.active_playing_context = None

    def start_pipeline(self, command: str, request_id: str | None = None) -> None:
        self.reset()
        ctx = TelemetryContext(command, request_id=request_id)
        self.set_thread_context(ctx)
        self.log_event("transcript received (STT complete)")

    def log_event(self, name: str):
        is_speech = "tts" in name.lower() or "playback" in name.lower() or "speech" in name.lower()
        
        if is_speech:
            ctx = self.active_playing_context or self.get_thread_context()
        else:
            ctx = self.get_thread_context() or self.active_playing_context

        if ctx is not None:
            elapsed = (time.time() - ctx.start_time) * 1000.0
            timestamp = time.strftime("%H:%M:%S") + f".{int((time.time() % 1) * 1000):03d}"
            ctx.events.append((name, elapsed, timestamp))
            logger.info(f"[TELEMETRY] [{ctx.command}] Event: {name} | Elapsed: {elapsed:.2f} ms")
        else:
            logger.info(f"[TELEMETRY] [No Context] Event: {name}")

    def print_summary(self):
        ctx = self.active_playing_context or self.get_thread_context()
        if ctx is not None:
            logger.info(f"=== PIPELINE TELEMETRY SUMMARY FOR: {ctx.command} ===")
            for name, elapsed, ts in ctx.events:
                logger.info(f"   {name:<45} | {elapsed:>8.2f} ms | {ts}")
            logger.info("=========================================================")
            
            if ctx == self.active_playing_context:
                self.active_playing_context = None
            else:
                self.set_thread_context(None)
        else:
            logger.warning("=== PIPELINE TELEMETRY SUMMARY FOR: None ===")

    def timed_stage(self, request_id: str, step_id: str, agent_role: str, stage_name: str):
        """Context manager timing a specific stage execution within an agent."""
        class StageContextManager:
            def __init__(self, timer, req_id, stp_id, role, stage):
                self.timer = timer
                self.req_id = req_id
                self.stp_id = stp_id
                self.role = role
                self.stage = stage
                self.start_t = 0.0

            def __enter__(self):
                self.start_t = time.time()
                self.timer.log_stage_event(self.req_id, self.stp_id, self.role, f"{self.stage}_start", 0.0)
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                dur_ms = (time.time() - self.start_t) * 1000.0
                self.timer.log_stage_event(self.req_id, self.stp_id, self.role, self.stage, dur_ms)

        return StageContextManager(self, request_id, step_id, agent_role, stage_name)

    def log_stage_event(self, request_id: str, step_id: str, agent_role: str, stage_name: str, duration_ms: float = 0.0):
        """Logs structured per-stage telemetry event with epoch timestamp for marker interval calculation."""
        ts = time.time()
        event_str = f"agent_stage:{request_id}:{step_id}:{agent_role}:{stage_name}:{duration_ms:.2f}ms:ts={ts:.6f}"
        self.log_event(event_str)

    def log_prompt_token_audit(
        self,
        request_id: str,
        step_id: str,
        agent_role: str,
        sys_inst: str = "",
        conv_hist: str = "",
        shared_ctx: str = "",
        memory_str: str = "",
        exec_meta: str = "",
        user_req: str = ""
    ):
        """Logs detailed per-agent prompt token breakdown audit (rough ~4 char per token metric)."""
        def estimate_tokens(s: str) -> int:
            return len(s) // 4 if s else 0

        c_sys = estimate_tokens(sys_inst)
        c_hist = estimate_tokens(conv_hist)
        c_ctx = estimate_tokens(shared_ctx)
        c_mem = estimate_tokens(memory_str)
        c_meta = estimate_tokens(exec_meta)
        c_req = estimate_tokens(user_req)
        c_total = c_sys + c_hist + c_ctx + c_mem + c_meta + c_req

        audit_str = (
            f"token_audit:{request_id}:{step_id}:{agent_role} | "
            f"sys={c_sys} hist={c_hist} ctx={c_ctx} mem={c_mem} meta={c_meta} req={c_req} | total={c_total}"
        )
        self.log_event(audit_str)


pipeline_timer = PipelineTimer.get_instance()
