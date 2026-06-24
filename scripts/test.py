from openai import OpenAI
import os

client = OpenAI(
    api_key=os.environ["OPENAI_API_KEY"],
    base_url="https://poloai.top/v1",
)

resp = client.chat.completions.create(
        model="gemini-3.1-pro-preview",  # 这里换成后台显示的精确模型名
        messages=[
            {"role": "user", "content": "Say only: OK"}
        ],
        temperature=0,
        max_tokens=20,
    )
print("调用成功")
print(resp.choices[0].message.content)