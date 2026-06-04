"""
Patch les dépendances d'infra (boto3, botocore, storage) avant leur import.
Permet de tester l'API sans MinIO ni variables d'environnement.
"""
from unittest.mock import MagicMock
import sys

# boto3/botocore non installés dans l'env de test
sys.modules.setdefault("boto3", MagicMock())
sys.modules.setdefault("botocore", MagicMock())
sys.modules.setdefault("botocore.client", MagicMock())

# storage.py lit des vars d'env à l'import — on le remplace entièrement
mock_storage = MagicMock()
mock_storage.ensure_bucket = MagicMock()
mock_storage.upload_artwork = MagicMock()
sys.modules["storage"] = mock_storage
