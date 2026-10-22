from fastapi import APIRouter

from nkz_soil.api.limiter import limiter
from nkz_soil.providers.metrics import metrics

router = APIRouter()


@router.get("/metrics")
@limiter.exempt
async def get_metrics():
    return {"providers": metrics.get_all_summaries()}


@router.get("/metrics/prometheus")
@limiter.exempt
async def prometheus_metrics():
    lines = []
    for summary in metrics.get_all_summaries():
        name = summary["provider"]
        lines.append('# HELP soil_provider_latency_ms Provider fetch latency in milliseconds')
        lines.append('# TYPE soil_provider_latency_ms gauge')
        lines.append(f'soil_provider_latency_ms{{provider="{name}",quantile="avg"}} {summary["latency"]["avg"]:.2f}')
        lines.append(f'soil_provider_latency_ms{{provider="{name}",quantile="p95"}} {summary["latency"]["p95"]:.2f}')
        lines.append(f'soil_provider_latency_ms{{provider="{name}",quantile="max"}} {summary["latency"]["max"]:.2f}')
        lines.append('# HELP soil_provider_error_rate Provider error rate')
        lines.append('# TYPE soil_provider_error_rate gauge')
        lines.append(f'soil_provider_error_rate{{provider="{name}"}} {summary["error_rate"]:.4f}')
        lines.append('# HELP soil_provider_cache_hit_rate Provider cache hit rate')
        lines.append('# TYPE soil_provider_cache_hit_rate gauge')
        lines.append(f'soil_provider_cache_hit_rate{{provider="{name}"}} {summary["cache"]["hit_rate"]:.4f}')
        lines.append('# HELP soil_provider_fetches_total Total provider fetches')
        lines.append('# TYPE soil_provider_fetches_total counter')
        lines.append(f'soil_provider_fetches_total{{provider="{name}"}} {summary["total_fetches"]}')
        lines.append('# HELP soil_provider_errors_total Total provider errors')
        lines.append('# TYPE soil_provider_errors_total counter')
        lines.append(f'soil_provider_errors_total{{provider="{name}"}} {summary["total_errors"]}')
    lines.append("")
    return "\n".join(lines)
