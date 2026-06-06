"""(Re)generate the Gujarati (*_gu) fields in data/degrees.json using Bhashini.

This satisfies the "data in Gujarati via Bhashini" requirement by translating the
English fields (degree_name, duration, fees, eligibility, required_documents) into
Gujarati with the Bhashini NMT API and writing them back.

Usage (from project root, with .env filled in):
    python -m scripts.translate_degrees
"""
import asyncio
import json

from app import bhashini, config

# (english_key -> gujarati_key)
SCALAR_FIELDS = {
    "degree_name": "degree_name_gu",
    "duration": "duration_gu",
    "fees": "fees_gu",
    "eligibility": "eligibility_gu",
}
LIST_FIELDS = {
    "required_documents": "required_documents_gu",
}


async def main() -> None:
    with open(config.DATA_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    for d in data["degrees"]:
        print(f"Translating: {d['id']}")
        for en_key, gu_key in SCALAR_FIELDS.items():
            d[gu_key] = await bhashini.translate(d[en_key], config.PIVOT_LANG, config.SOURCE_LANG)
        for en_key, gu_key in LIST_FIELDS.items():
            d[gu_key] = [
                await bhashini.translate(item, config.PIVOT_LANG, config.SOURCE_LANG)
                for item in d[en_key]
            ]

    with open(config.DATA_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    await bhashini.aclose()
    print("\nDone. data/degrees.json updated with fresh Gujarati fields.")


if __name__ == "__main__":
    asyncio.run(main())
