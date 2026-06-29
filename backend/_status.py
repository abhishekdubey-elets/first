import os
from huggingface_hub import HfApi
api=HfApi()
rt=api.get_space_runtime(repo_id="abhishek-elets/ias-transfer-intelligence", token=os.environ["HF_TOKEN"])
print("stage:", rt.stage, "| hardware:", rt.hardware)
