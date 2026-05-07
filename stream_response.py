from openai import OpenAI

client = OpenAI()

question = "Solve this step by step: why does the harmonic series diverge?"

stream = client.responses.create(
    model="gpt-5.5-pro",
    input=question,
    stream=True,
    reasoning={
        "effort": "high",
        "summary": "detailed"
    }
)

print("\n=== LIVE REASONING SUMMARY ===\n")
printed_reasoning = False
printed_answer = False

for event in stream:
    if event.type == "response.reasoning_summary_text.delta":
        if not printed_reasoning:
            printed_reasoning = True
        print(event.delta, end="", flush=True)

    elif event.type == "response.output_text.delta":
        if not printed_answer:
            printed_answer = True
            print("\n\n=== ANSWER ===\n")
        print(event.delta, end="", flush=True)

    elif event.type == "response.completed":
        print("\n\n[done]")