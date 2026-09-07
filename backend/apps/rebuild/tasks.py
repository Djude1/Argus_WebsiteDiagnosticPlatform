import logging

from celery import shared_task

from apps.rebuild.models import SiteRebuild
from apps.rebuild.services import ask_followup, run_rebuild

logger = logging.getLogger(__name__)


@shared_task(bind=True)
def run_site_rebuild(self, rebuild_id: int) -> dict:
    """執行一次複刻 + 優化。

    不重試：優化會花錢，自動重試等於在使用者沒同意的情況下重複計費。
    失敗原因已寫進 SiteRebuild.error，使用者看得到，要重跑由他自己按。
    """
    rebuild = SiteRebuild.objects.filter(pk=rebuild_id).select_related("page").first()
    if rebuild is None:
        logger.warning("SiteRebuild %s 不存在，略過", rebuild_id)
        return {"rebuild_id": rebuild_id, "status": "missing"}

    run_rebuild(rebuild)
    return {"rebuild_id": rebuild.pk, "status": rebuild.status}


@shared_task(bind=True)
def ask_rebuild_agent(self, rebuild_id: int, question: str) -> dict:
    """在既有 session 裡追問。同樣不重試——每一輪都花錢。"""
    rebuild = SiteRebuild.objects.filter(pk=rebuild_id).select_related(
        "page", "scan_job"
    ).first()
    if rebuild is None:
        logger.warning("SiteRebuild %s 不存在，略過追問", rebuild_id)
        return {"rebuild_id": rebuild_id, "status": "missing"}
    ask_followup(rebuild, question)
    return {"rebuild_id": rebuild.pk, "status": rebuild.status}
