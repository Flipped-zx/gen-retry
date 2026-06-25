from openai import OpenAI
import os

# 组里
# client = OpenAI(
#     api_key="sk-ODVjJJezsXz8F48I0toWYPWNMkPM2XONTHaCN7Lsp3aNmIGL",
#     base_url="https://yunwu.ai/v1",
# )


# 自建平台
client = OpenAI(
    api_key="sk-fa1a5f266f9cbae1a9430e23fbea75ed473186471263f18c5e4fee8d2092230c",
    base_url="https://skyapi.duckdns.org/v1",
)
# models_id
models = client.models.list()

print("包含 gpt 的模型：")

found = False
for m in models.data:
    model_id = m.id
    if "gpt" in model_id.lower():
        print(model_id)
        found = True

if not found:
    print("没有找到包含 gemini 的模型")

# 调用models
# resp = client.chat.completions.create(
#         model="gemini-3.1-pro-preview",  # 这里换成后台显示的精确模型名
#         messages=[
#             {"role": "user", "content": "Say only: OK"}
#         ],
#         temperature=0,
#         max_tokens=20,
#     )
# print("调用成功")
# print(resp.choices[0].message.content)