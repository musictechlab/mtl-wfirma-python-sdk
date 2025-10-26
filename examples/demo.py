import os
import json
from dotenv import load_dotenv
from wfirma_sdk import WFirmaAPIClient

load_dotenv()


print(os.getenv("WFIRMA_COMPANY_ID"))
print(os.getenv("WFIRMA_ACCESS_KEY"))
print(os.getenv("WFIRMA_SECRET_KEY"))
print(os.getenv("WFIRMA_APP_KEY"))


def main():
    access_key = os.getenv("WFIRMA_ACCESS_KEY")
    secret_key = os.getenv("WFIRMA_SECRET_KEY")
    app_key = os.getenv("WFIRMA_APP_KEY")

    company_id = os.getenv("WFIRMA_COMPANY_ID")

    client = WFirmaAPIClient(
        company_id=company_id,
        access_key=access_key,
        secret_key=secret_key,
        app_key=app_key,
    )

    # prosty przykład zapytania find (20 najnowszych faktur)
    xml_body = b"""<?xml version="1.0" encoding="UTF-8"?>
    <api>
        <invoices>
            <parameters>
                <page>1</page>
                <limit>20</limit>
                <order>
                    <desc>date</desc>
                </order>
            </parameters>
        </invoices>
    </api>"""

    response = client.invoices.find(parameters_xml=xml_body)
    print(json.dumps(response, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
