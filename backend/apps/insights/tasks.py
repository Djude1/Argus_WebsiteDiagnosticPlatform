from celery import shared_task

from apps.insights import pagespeed_jobs


@shared_task(ignore_result=True)
def run_public_pagespeed(job_id: str, url: str) -> None:
    """快速檢查頁測速的 Google PageSpeed Insights 量測（見 pagespeed_jobs）。"""
    pagespeed_jobs.run(job_id, url)
