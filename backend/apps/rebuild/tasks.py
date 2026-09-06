import logging

from celery import shared_task

from apps.rebuild.models import SiteRebuild
from apps.rebuild.services import run_rebuild

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
