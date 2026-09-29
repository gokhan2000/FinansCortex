"""Programi ve veriyi Hugging Face Space'ine (ozel) yukler.

HF_YUKLE.bat cift tiklaninca calisir. Anahtar (token) sorulur, ekrana
yazilirken gorunmez, hicbir yere kaydedilmez.

  python scripts/hf_yukle.py          kod + veri (~240 MB, ilk sefer)
  python scripts/hf_yukle.py kod      yalniz kod (hizli; veri Space'te kalir)
"""

from __future__ import annotations

import getpass
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
UYGULAMA = "deepcortex"

KOD = ["app.py", "requirements.txt", "ui/**", "src/**", ".streamlit/**",
       "config/stratejiler.json"]
VERI = ["data/market.duckdb"]


def main() -> None:
    sadece_kod = len(sys.argv) > 1 and sys.argv[1].lower() == "kod"

    token = getpass.getpass("Hugging Face anahtari (yazarken gorunmez): ").strip()
    api = HfApi(token=token)
    kullanici = api.whoami()["name"]
    repo = f"{kullanici}/{UYGULAMA}"

    api.create_repo(repo, repo_type="space", space_sdk="streamlit",
                    private=True, exist_ok=True)
    print(f"Space hazir (ozel): {repo}")

    print("Kod yukleniyor...")
    api.upload_folder(
        folder_path=str(ROOT), repo_id=repo, repo_type="space",
        allow_patterns=KOD, ignore_patterns=["**/__pycache__/**", "*.pyc"],
        commit_message="Kod",
    )
    for ad in ("README.md",):
        api.upload_file(path_or_fileobj=str(ROOT / "hf" / ad), path_in_repo=ad,
                        repo_id=repo, repo_type="space", commit_message=ad)

    if not sadece_kod:
        print("Veri yukleniyor (~240 MB, birkac dakika)...")
        api.upload_folder(
            folder_path=str(ROOT), repo_id=repo, repo_type="space",
            allow_patterns=VERI, commit_message="Veri",
        )

    print()
    print("TAMAM. Program kurulup acilirken birkac dakika bekleyin.")
    print(f"Adres (yalniz sen, giris yaparak): https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()
