"""drf-spectacular 的 schema 後處理。

回應 schema 的「必填」判定：drf-spectacular 只把 `required=True` 或唯讀欄位
標為必填。ModelSerializer 對「model 欄位有 default」的欄位會設 `required=False`
（那是寫入端的語意：不給就用預設值），結果連回應都被標成選填，前端型別因此
變成 `status?: ...`、`balance?: number`，被迫到處處理「不會發生的缺欄位」。

實際上 DRF 序列化 model instance 時一定輸出每個可讀欄位；可能為空的欄位
另有 `allow_null`（型別上是 `| null`），與「選填」是兩回事。所以這裡把回應用的
component 全部欄位標為必填。

請求用的 component（COMPONENT_SPLIT_REQUEST 產生的 `…Request`）維持原樣，
寫入端「可以不給」的語意不能改。

此假設由 apps/admin_api/tests.py::AdminResponseMatchesSchemaTests 驗證：
打實際端點，回傳的鍵集合必須等於 schema 宣告的欄位集合。
"""


def mark_response_fields_required(result, generator, request, public):
    for name, component in result.get("components", {}).get("schemas", {}).items():
        if name.endswith("Request"):
            continue
        properties = component.get("properties")
        if properties:
            component["required"] = sorted(properties)
    return result
