#!/usr/bin/env python3

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from models import SyncAction, SyncPlan, SyncResult


class AuditLogger:

    def __init__(self, log_dir: str = ".", prefix: str = "audit"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        self.log_file = self.log_dir / f"{prefix}_{timestamp}.jsonl"
        self.records: list[dict] = []

    def log_action(
        self,
        action: SyncAction,
        org_name: str,
        dry_run: bool = False,
    ) -> None:
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "org": org_name,
            "dry_run": dry_run,
            "action_type": action.action_type.value,
            "resource": action.resource,
            "details": action.details,
            "status": action.status.value,
            "message": action.message,
            "error": action.error,
        }
        self.records.append(record)
        self._append_record(record)

    def log_plan(self, plan: SyncPlan, dry_run: bool = False) -> None:
        for action in plan.sorted_actions:
            self.log_action(action, plan.org_name, dry_run)

    def log_result(self, result: SyncResult) -> None:
        summary_record = {
            "timestamp": result.executed_at,
            "type": "sync_summary",
            "org": result.plan.org_name,
            "dry_run": result.dry_run,
            "success": result.success,
            "success_count": result.success_count,
            "failure_count": result.failure_count,
            "skipped_count": result.skipped_count,
            "total_actions": len(result.plan.actions),
        }
        self._append_record(summary_record)
        self.log_plan(result.plan, result.dry_run)

    def _append_record(self, record: dict) -> None:
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception as e:
            logging.error(f"Failed to write audit log: {e}")

    @property
    def log_path(self) -> str:
        return str(self.log_file)

    def get_summary(self) -> str:
        success = sum(1 for r in self.records if r.get("status") == "success")
        failed = sum(1 for r in self.records if r.get("status") == "failed")
        skipped = sum(1 for r in self.records if r.get("status") == "skipped")
        return (
            f"Audit log: {self.log_file}\n"
            f"  Records: {len(self.records)}\n"
            f"  Success: {success} | Failed: {failed} | Skipped: {skipped}"
        )
