"""Deterministic, read-only readiness evaluation with no activation path."""

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256

import orjson
from pydantic import BaseModel

from quantforge.readiness.models import (
    GateEvaluation,
    GateName,
    GateStatus,
    ReadinessEvidence,
    ReadinessPolicy,
    ReadinessReport,
    ReadinessStatus,
)

SECONDS_PER_DAY = Decimal("86400")
SECONDS_PER_HOUR = 3600


def _digest_model(value: BaseModel) -> str:
    payload = value.model_dump(mode="json")
    return sha256(orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)).hexdigest()


def _text(value: object) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


class ReadinessEvaluator:
    """Classify evidence; never mutate settings, approvals, releases, or execution state."""

    def evaluate(
        self,
        evidence: ReadinessEvidence,
        policy: ReadinessPolicy,
        *,
        evaluated_at_utc: datetime | None = None,
    ) -> ReadinessReport:
        evaluated_at = evaluated_at_utc or datetime.now(UTC)
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() != UTC.utcoffset(evaluated_at):
            raise ValueError("evaluation timestamp must be UTC-aware")
        gates = (
            self._paper_history(evidence, policy, evaluated_at),
            self._reconciliation(evidence, policy, evaluated_at),
            self._data_availability(evidence, policy, evaluated_at),
            self._incidents(evidence, policy, evaluated_at),
            self._model_stability(evidence, policy, evaluated_at),
            self._drawdown_expectancy(evidence, policy, evaluated_at),
            self._cost_model(evidence, policy, evaluated_at),
            self._order_test(evidence, policy, evaluated_at),
            self._backup_restore(evidence, policy, evaluated_at),
            self._security(evidence, policy, evaluated_at),
            self._operator_runbook(evidence, policy, evaluated_at),
            self._live_locks(evidence, policy, evaluated_at),
            self._release_approval(evidence, policy, evaluated_at),
        )
        statuses = tuple(gate.status for gate in gates)
        status = (
            ReadinessStatus.NOT_READY
            if GateStatus.FAIL in statuses
            else ReadinessStatus.CONDITIONALLY_READY
            if GateStatus.CONDITIONAL in statuses
            else ReadinessStatus.READY_FOR_MANUAL_CANARY_REVIEW
        )
        return ReadinessReport(
            evaluated_at_utc=evaluated_at,
            evidence_id=evidence.evidence_id,
            source_revision=evidence.source_revision,
            policy_version=policy.policy_version,
            evidence_sha256=_digest_model(evidence),
            policy_sha256=_digest_model(policy),
            status=status,
            gates=gates,
        )

    def _common_failures(
        self,
        *,
        generated_at_utc: datetime,
        observed_at_utc: datetime,
        evaluated_at_utc: datetime,
        policy: ReadinessPolicy,
    ) -> list[str]:
        failures: list[str] = []
        future_limit = Decimal(policy.maximum_future_skew_seconds)
        generated_future = Decimal(str((generated_at_utc - evaluated_at_utc).total_seconds()))
        observed_future = Decimal(str((observed_at_utc - generated_at_utc).total_seconds()))
        age_hours = Decimal(str((evaluated_at_utc - generated_at_utc).total_seconds())) / Decimal(
            SECONDS_PER_HOUR
        )
        if generated_future > future_limit:
            failures.append("evidence bundle is future-dated")
        if observed_future > future_limit:
            failures.append("component observation is later than the evidence bundle")
        if age_hours > policy.maximum_evidence_age_hours:
            failures.append("evidence bundle is stale")
        return failures

    @staticmethod
    def _result(
        gate: GateName,
        observed: tuple[tuple[str, object], ...],
        required: tuple[tuple[str, object], ...],
        hard_failures: list[str],
        conditional_reasons: list[str],
    ) -> GateEvaluation:
        status = (
            GateStatus.FAIL
            if hard_failures
            else GateStatus.CONDITIONAL
            if conditional_reasons
            else GateStatus.PASS
        )
        reasons = tuple(hard_failures or conditional_reasons or ("all preferred criteria passed",))
        return GateEvaluation(
            gate=gate,
            status=status,
            observed=tuple((name, _text(value)) for name, value in observed),
            required=tuple((name, _text(value)) for name, value in required),
            reasons=reasons,
        )

    @staticmethod
    def _missing(gate: GateName) -> GateEvaluation:
        return GateEvaluation(
            gate=gate,
            status=GateStatus.FAIL,
            observed=(("evidence", "missing"),),
            required=(("evidence", "present and valid"),),
            reasons=("required evidence is missing",),
        )

    def _paper_history(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.paper_history
        if item is None:
            return self._missing(GateName.PAPER_HISTORY)
        days = Decimal(str((item.period_end_utc - item.period_start_utc).total_seconds())) / (
            SECONDS_PER_DAY
        )
        regimes = len(item.observed_regimes)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        if days < policy.hard_minimum_paper_days:
            hard.append("paper calendar duration is below the hard minimum")
        elif days < policy.preferred_minimum_paper_days:
            conditional.append("paper calendar duration is below the preferred minimum")
        if item.trade_count < policy.hard_minimum_paper_trades:
            hard.append("paper trade count is below the hard minimum")
        elif item.trade_count < policy.preferred_minimum_paper_trades:
            conditional.append("paper trade count is below the preferred minimum")
        if regimes < policy.hard_minimum_regime_count:
            hard.append("observed regime count is below the hard minimum")
        elif regimes < policy.preferred_minimum_regime_count:
            conditional.append("observed regime count is below the preferred minimum")
        return self._result(
            GateName.PAPER_HISTORY,
            (("paper_days", days), ("trade_count", item.trade_count), ("regime_count", regimes)),
            (
                ("hard_days", policy.hard_minimum_paper_days),
                ("preferred_days", policy.preferred_minimum_paper_days),
                ("hard_trades", policy.hard_minimum_paper_trades),
                ("preferred_trades", policy.preferred_minimum_paper_trades),
                ("hard_regimes", policy.hard_minimum_regime_count),
                ("preferred_regimes", policy.preferred_minimum_regime_count),
            ),
            hard,
            conditional,
        )

    def _reconciliation(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.reconciliation
        if item is None:
            return self._missing(GateName.RECONCILIATION)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        if item.mismatch_count:
            hard.append("reconciliation mismatches must be zero")
        if item.unknown_order_count:
            hard.append("unknown orders must be zero")
        if item.last_success_at_utc is None:
            hard.append("last successful reconciliation evidence is missing")
        elif (now - item.last_success_at_utc).total_seconds() > (
            policy.maximum_evidence_age_hours * SECONDS_PER_HOUR
        ):
            hard.append("last successful reconciliation is stale")
        if item.successful_days < policy.hard_minimum_reconciliation_days:
            hard.append("successful reconciliation days are below the hard minimum")
        elif item.successful_days < policy.preferred_minimum_reconciliation_days:
            conditional.append("successful reconciliation days are below the preferred minimum")
        return self._result(
            GateName.RECONCILIATION,
            (
                ("successful_days", item.successful_days),
                ("runs", item.reconciliation_runs),
                ("mismatches", item.mismatch_count),
                ("unknown_orders", item.unknown_order_count),
            ),
            (
                ("hard_days", policy.hard_minimum_reconciliation_days),
                ("preferred_days", policy.preferred_minimum_reconciliation_days),
                ("mismatches", 0),
                ("unknown_orders", 0),
            ),
            hard,
            conditional,
        )

    def _data_availability(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.data_availability
        if item is None:
            return self._missing(GateName.DATA_AVAILABILITY)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        if not item.schema_compatible:
            hard.append("data schema is incompatible")
        if item.checksum_failure_count:
            hard.append("data checksum failures must be zero")
        if item.freshest_event_at_utc is None:
            hard.append("freshest data event timestamp is missing")
        elif (now - item.freshest_event_at_utc).total_seconds() > (
            policy.maximum_data_event_age_seconds
        ):
            hard.append("market data is stale")
        if item.availability_ratio < policy.hard_minimum_data_availability_ratio:
            hard.append("data availability is below the hard minimum")
        elif item.availability_ratio < policy.preferred_minimum_data_availability_ratio:
            conditional.append("data availability is below the preferred minimum")
        if item.window_days < policy.hard_minimum_paper_days:
            hard.append("data availability window is below the hard minimum")
        elif item.window_days < policy.preferred_minimum_paper_days:
            conditional.append("data availability window is below the preferred minimum")
        return self._result(
            GateName.DATA_AVAILABILITY,
            (
                ("window_days", item.window_days),
                ("availability_ratio", item.availability_ratio),
                ("gaps", item.gap_count),
                ("checksum_failures", item.checksum_failure_count),
                ("schema_compatible", item.schema_compatible),
            ),
            (
                ("hard_ratio", policy.hard_minimum_data_availability_ratio),
                ("preferred_ratio", policy.preferred_minimum_data_availability_ratio),
                ("checksum_failures", 0),
                ("schema_compatible", True),
            ),
            hard,
            conditional,
        )

    def _incidents(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.incidents
        if item is None:
            return self._missing(GateName.INCIDENTS)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        if item.window_days < policy.hard_minimum_paper_days:
            hard.append("incident observation window is below the hard minimum")
        elif item.window_days < policy.preferred_minimum_paper_days:
            conditional.append("incident observation window is below the preferred minimum")
        if item.unresolved_critical:
            hard.append("unresolved critical incidents must be zero")
        if item.unresolved_high > policy.maximum_unresolved_high_incidents:
            hard.append("unresolved high incidents exceed the hard maximum")
        elif item.unresolved_high > policy.preferred_unresolved_high_incidents:
            conditional.append("unresolved high incidents exceed the preferred maximum")
        high_rate = Decimal(item.high_opened * 30) / Decimal(item.window_days)
        if high_rate > policy.hard_maximum_high_incidents_per_30_days:
            hard.append("high incident rate exceeds the hard maximum")
        elif high_rate > policy.preferred_maximum_high_incidents_per_30_days:
            conditional.append("high incident rate exceeds the preferred maximum")
        if item.critical_opened > policy.maximum_critical_incidents_in_window:
            hard.append("critical incident count exceeds the hard maximum")
        elif item.critical_opened > policy.preferred_critical_incidents_in_window:
            conditional.append("critical incident count exceeds the preferred maximum")
        return self._result(
            GateName.INCIDENTS,
            (
                ("window_days", item.window_days),
                ("unresolved_critical", item.unresolved_critical),
                ("unresolved_high", item.unresolved_high),
                ("critical_opened", item.critical_opened),
                ("high_opened", item.high_opened),
                ("high_incidents_per_30_days", high_rate),
            ),
            (
                ("unresolved_critical", 0),
                ("hard_unresolved_high", policy.maximum_unresolved_high_incidents),
                ("preferred_unresolved_high", policy.preferred_unresolved_high_incidents),
                (
                    "hard_high_incidents_per_30_days",
                    policy.hard_maximum_high_incidents_per_30_days,
                ),
                (
                    "preferred_high_incidents_per_30_days",
                    policy.preferred_maximum_high_incidents_per_30_days,
                ),
            ),
            hard,
            conditional,
        )

    def _model_stability(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.model_stability
        if item is None:
            return self._missing(GateName.MODEL_STABILITY)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        if not item.artifact_integrity_verified:
            hard.append("active model artifact integrity is not verified")
        if item.stability_days < policy.hard_minimum_model_stability_days:
            hard.append("model stability duration is below the hard minimum")
        elif item.stability_days < policy.preferred_minimum_model_stability_days:
            conditional.append("model stability duration is below the preferred minimum")
        if item.calibration_error > policy.hard_maximum_calibration_error:
            hard.append("model calibration error exceeds the hard maximum")
        elif item.calibration_error > policy.preferred_maximum_calibration_error:
            conditional.append("model calibration error exceeds the preferred maximum")
        if item.drift_score > policy.hard_maximum_model_drift_score:
            hard.append("model drift exceeds the hard maximum")
        elif item.drift_score > policy.preferred_maximum_model_drift_score:
            conditional.append("model drift exceeds the preferred maximum")
        return self._result(
            GateName.MODEL_STABILITY,
            (
                ("stability_days", item.stability_days),
                ("calibration_error", item.calibration_error),
                ("drift_score", item.drift_score),
                ("artifact_count", len(item.active_artifact_hashes)),
            ),
            (
                ("hard_stability_days", policy.hard_minimum_model_stability_days),
                ("preferred_stability_days", policy.preferred_minimum_model_stability_days),
                ("hard_calibration", policy.hard_maximum_calibration_error),
                ("preferred_calibration", policy.preferred_maximum_calibration_error),
                ("hard_drift", policy.hard_maximum_model_drift_score),
                ("preferred_drift", policy.preferred_maximum_model_drift_score),
            ),
            hard,
            conditional,
        )

    def _drawdown_expectancy(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.performance
        if item is None:
            return self._missing(GateName.DRAWDOWN_EXPECTANCY)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        if not item.all_costs_included:
            hard.append("performance evidence does not include all modeled costs")
        if item.maximum_drawdown_ratio > policy.hard_maximum_drawdown_ratio:
            hard.append("paper drawdown exceeds the hard maximum")
        elif item.maximum_drawdown_ratio > policy.preferred_maximum_drawdown_ratio:
            conditional.append("paper drawdown exceeds the preferred maximum")
        if item.cost_adjusted_expectancy_lower_bps < policy.hard_minimum_expectancy_lower_bps:
            hard.append("cost-adjusted expectancy lower bound is below the hard minimum")
        elif (
            item.cost_adjusted_expectancy_lower_bps < policy.preferred_minimum_expectancy_lower_bps
        ):
            conditional.append(
                "cost-adjusted expectancy lower bound is below the preferred minimum"
            )
        return self._result(
            GateName.DRAWDOWN_EXPECTANCY,
            (
                ("trade_count", item.paper_trade_count),
                ("maximum_drawdown_ratio", item.maximum_drawdown_ratio),
                ("expectancy_lower_bps", item.cost_adjusted_expectancy_lower_bps),
                ("all_costs_included", item.all_costs_included),
            ),
            (
                ("hard_drawdown", policy.hard_maximum_drawdown_ratio),
                ("preferred_drawdown", policy.preferred_maximum_drawdown_ratio),
                ("hard_expectancy", policy.hard_minimum_expectancy_lower_bps),
                ("preferred_expectancy", policy.preferred_minimum_expectancy_lower_bps),
            ),
            hard,
            conditional,
        )

    def _cost_model(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.cost_model
        if item is None:
            return self._missing(GateName.COST_MODEL)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        conditional: list[str] = []
        included = (
            item.includes_fees
            and item.includes_spread
            and item.includes_slippage
            and item.includes_latency
            and item.includes_adverse_selection
        )
        if not included:
            hard.append("cost model omits a required cost component")
        if item.observation_count < policy.hard_minimum_cost_observations:
            hard.append("cost calibration observations are below the hard minimum")
        elif item.observation_count < policy.preferred_minimum_cost_observations:
            conditional.append("cost calibration observations are below the preferred minimum")
        if item.mean_absolute_error_bps > policy.hard_maximum_cost_error_bps:
            hard.append("cost model error exceeds the hard maximum")
        elif item.mean_absolute_error_bps > policy.preferred_maximum_cost_error_bps:
            conditional.append("cost model error exceeds the preferred maximum")
        return self._result(
            GateName.COST_MODEL,
            (
                ("observation_count", item.observation_count),
                ("mean_absolute_error_bps", item.mean_absolute_error_bps),
                ("all_cost_components", included),
            ),
            (
                ("hard_observations", policy.hard_minimum_cost_observations),
                ("preferred_observations", policy.preferred_minimum_cost_observations),
                ("hard_error_bps", policy.hard_maximum_cost_error_bps),
                ("preferred_error_bps", policy.preferred_maximum_cost_error_bps),
            ),
            hard,
            conditional,
        )

    def _order_test(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.order_test
        if item is None:
            return self._missing(GateName.ORDER_TEST)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        if not item.endpoint_supported_by_manifest:
            hard.append("order-test capability is not supported by the reviewed manifest")
        if not item.dry_run_verified or item.completed_at_utc is None:
            hard.append("reviewed order-test dry-run evidence is missing")
        elif (now - item.completed_at_utc).total_seconds() > (
            policy.maximum_order_test_age_days * int(SECONDS_PER_DAY)
        ):
            hard.append("order-test evidence is stale")
        return self._result(
            GateName.ORDER_TEST,
            (
                ("manifest_supported", item.endpoint_supported_by_manifest),
                ("dry_run_verified", item.dry_run_verified),
                ("real_order_created", item.real_order_created),
            ),
            (("maximum_age_days", policy.maximum_order_test_age_days),),
            hard,
            [],
        )

    def _backup_restore(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.backup_restore
        if item is None:
            return self._missing(GateName.BACKUP_RESTORE)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        required_true = (
            item.restore_verified,
            item.checksum_verified,
            item.isolated_target,
            item.production_grade,
            item.encrypted,
            item.off_host,
            item.objectives_measured,
        )
        if not all(required_true):
            hard.append("production-grade backup/restore evidence is incomplete")
        if item.tested_at_utc is None:
            hard.append("restore drill timestamp is missing")
        elif (now - item.tested_at_utc).total_seconds() > (
            policy.maximum_restore_age_days * int(SECONDS_PER_DAY)
        ):
            hard.append("restore drill evidence is stale")
        return self._result(
            GateName.BACKUP_RESTORE,
            (
                ("restore_verified", item.restore_verified),
                ("checksum_verified", item.checksum_verified),
                ("production_grade", item.production_grade),
                ("encrypted", item.encrypted),
                ("off_host", item.off_host),
                ("objectives_measured", item.objectives_measured),
            ),
            (("maximum_age_days", policy.maximum_restore_age_days),),
            hard,
            [],
        )

    def _security(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.security
        if item is None:
            return self._missing(GateName.SECURITY)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        required_true = (
            item.audit_passed,
            item.secret_scan_passed,
            item.dependency_audit_passed,
            item.dashboard_auth_reviewed,
            item.network_policy_reviewed,
            item.withdrawal_permission_disabled,
            item.api_key_ip_allowlist_reviewed,
            item.live_gates_tested,
        )
        if not all(required_true) or item.high_or_critical_findings:
            hard.append("security review is incomplete or has high/critical findings")
        if item.completed_at_utc is None:
            hard.append("security audit timestamp is missing")
        elif (now - item.completed_at_utc).total_seconds() > (
            policy.maximum_security_audit_age_days * int(SECONDS_PER_DAY)
        ):
            hard.append("security audit evidence is stale")
        return self._result(
            GateName.SECURITY,
            (
                ("audit_passed", item.audit_passed),
                ("high_or_critical_findings", item.high_or_critical_findings),
                ("secret_scan_passed", item.secret_scan_passed),
                ("dependency_audit_passed", item.dependency_audit_passed),
            ),
            (("maximum_age_days", policy.maximum_security_audit_age_days),),
            hard,
            [],
        )

    def _operator_runbook(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.operator_runbook
        if item is None:
            return self._missing(GateName.OPERATOR_RUNBOOK)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        drills = (
            item.incident_drill_passed,
            item.cancel_only_drill_passed,
            item.reconciliation_drill_passed,
            item.recovery_drill_passed,
        )
        if not item.verified or not all(drills):
            hard.append("operator runbook or required drills are not verified")
        if item.reviewed_operator_count < policy.minimum_reviewed_operators:
            hard.append("too few operators reviewed the runbook")
        if item.completed_at_utc is None:
            hard.append("runbook review timestamp is missing")
        elif (now - item.completed_at_utc).total_seconds() > (
            policy.maximum_runbook_review_age_days * int(SECONDS_PER_DAY)
        ):
            hard.append("operator runbook evidence is stale")
        return self._result(
            GateName.OPERATOR_RUNBOOK,
            (
                ("verified", item.verified),
                ("reviewed_operators", item.reviewed_operator_count),
                ("all_drills_passed", all(drills)),
            ),
            (
                ("minimum_operators", policy.minimum_reviewed_operators),
                ("maximum_age_days", policy.maximum_runbook_review_age_days),
            ),
            hard,
            [],
        )

    def _live_locks(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.live_locks
        if item is None:
            return self._missing(GateName.LIVE_LOCKS)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        locks = (
            item.default_mode_paper,
            item.order_submission_default_false,
            item.six_gate_guard_verified,
            item.single_flag_cannot_enable_live,
            item.operator_unlock_absent,
            item.live_adapter_implemented_and_reviewed,
            item.order_network_allowlist_reviewed,
        )
        if not all(locks):
            hard.append("one or more mandatory live locks are not verified closed")
        return self._result(
            GateName.LIVE_LOCKS,
            (
                ("default_mode_paper", item.default_mode_paper),
                ("order_submission_default_false", item.order_submission_default_false),
                ("six_gate_guard_verified", item.six_gate_guard_verified),
                ("single_flag_cannot_enable", item.single_flag_cannot_enable_live),
                ("operator_unlock_absent", item.operator_unlock_absent),
                ("live_adapter_reviewed", item.live_adapter_implemented_and_reviewed),
                ("order_network_allowlist_reviewed", item.order_network_allowlist_reviewed),
                ("validator_order_capability", item.validator_has_order_capability),
            ),
            (("all_runtime_locks_closed", True),),
            hard,
            [],
        )

    def _release_approval(
        self, evidence: ReadinessEvidence, policy: ReadinessPolicy, now: datetime
    ) -> GateEvaluation:
        item = evidence.release_approval
        if item is None:
            return self._missing(GateName.RELEASE_APPROVAL)
        hard = self._common_failures(
            generated_at_utc=evidence.generated_at_utc,
            observed_at_utc=item.observed_at_utc,
            evaluated_at_utc=now,
            policy=policy,
        )
        plan = item.canary_plan
        if len(plan.markets) > policy.maximum_canary_markets:
            hard.append("canary market count exceeds the reviewed maximum")
        if plan.maximum_order_notional_krw > policy.maximum_canary_order_notional_krw:
            hard.append("canary order notional exceeds the reviewed maximum")
        if plan.maximum_total_exposure_krw > policy.maximum_canary_total_exposure_krw:
            hard.append("canary exposure exceeds the reviewed maximum")
        if plan.maximum_duration_minutes > policy.maximum_canary_duration_minutes:
            hard.append("canary duration exceeds the reviewed maximum")
        return self._result(
            GateName.RELEASE_APPROVAL,
            (
                ("approved_code_revision", item.approved_code_revision),
                ("approved_model_count", len(item.approved_model_hashes)),
                ("canary_market_count", len(plan.markets)),
                ("maximum_order_notional_krw", plan.maximum_order_notional_krw),
                ("maximum_total_exposure_krw", plan.maximum_total_exposure_krw),
                ("maximum_duration_minutes", plan.maximum_duration_minutes),
            ),
            (
                ("maximum_markets", policy.maximum_canary_markets),
                ("maximum_order_notional_krw", policy.maximum_canary_order_notional_krw),
                ("maximum_total_exposure_krw", policy.maximum_canary_total_exposure_krw),
                ("maximum_duration_minutes", policy.maximum_canary_duration_minutes),
                ("human_approval_required", True),
            ),
            hard,
            [],
        )
