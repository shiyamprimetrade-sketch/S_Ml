"""Invented fixture; not account data or training observations."""
from s_ml.ingestion import FIELDS


def sample():
    return {'schema': 's_ml.metricool-export.v1', 'source': 'metricool_authorized_connector',
            'account': 'example_account', 'brand_id': '123', 'timezone': 'Asia/Dhaka',
            'observed_at': '2026-11-14T20:00:00+06:00', 'fields': list(FIELDS),
            'rows': [['20261113180000', 'https://www.tiktok.com/@example_account/video/123456',
                      'Synthetic fixture', '9', '84', '1', '0', '0', None, None, None, None, 'VIDEO']]}
