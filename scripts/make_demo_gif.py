from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    output = Path("docs/assets/sensecllm-demo.gif")
    output.parent.mkdir(parents=True, exist_ok=True)
    stages = ["Document", "Recall", "Mechanism", "Refine", "Vulnerability", "Critic", "Experiment", "Defense"]
    frames = []
    font = ImageFont.load_default(size=18)
    small = ImageFont.load_default(size=14)
    for active in range(len(stages) + 2):
        image = Image.new("RGB", (1200, 630), "#08111d")
        draw = ImageDraw.Draw(image)
        draw.text((55, 45), "SenseCLLM Agent Harness", fill="#e9f2fa", font=font)
        draw.text((55, 78), "Physics-constrained multi-Agent sensor security analysis", fill="#9eb2c8", font=small)
        draw.rounded_rectangle((45, 125, 1155, 290), 18, fill="#101d2d", outline="#29415e", width=2)
        x, y = 70, 185
        for index, stage in enumerate(stages):
            width = 112
            color = "#56d6c9" if index < active else "#f4c56a" if index == active else "#42617f"
            draw.rounded_rectangle((x, y, x + width, y + 48), 20, outline=color, width=3)
            draw.text((x + 9, y + 15), stage, fill=color, font=small)
            if index < len(stages) - 1:
                draw.line((x + width, y + 24, x + width + 18, y + 24), fill="#42617f", width=2)
            x += 132
        draw.rounded_rectangle((45, 320, 730, 575), 18, fill="#101d2d", outline="#29415e", width=2)
        draw.text((70, 345), "Accepted physical paths", fill="#e9f2fa", font=font)
        path_lines = [
            "Acoustic source → MEMS transducer → saturation → ADC",
            "EM field → conductive interconnect → antenna effect → amplifier",
            "Evidence and target facts retain separate provenance",
        ]
        for row, line in enumerate(path_lines):
            draw.text((75, 395 + row * 48), "✓ " + line, fill="#56d6c9", font=small)
        draw.rounded_rectangle((760, 320, 1155, 575), 18, fill="#101d2d", outline="#29415e", width=2)
        draw.text((785, 345), "Run telemetry", fill="#e9f2fa", font=font)
        status = "completed" if active >= len(stages) else f"running · {stages[min(active, len(stages)-1)]}"
        draw.text((785, 402), status, fill="#f4c56a" if active < len(stages) else "#56d6c9", font=small)
        draw.text((785, 450), "checkpoint · SSE · traces · tokens", fill="#9eb2c8", font=small)
        draw.text((785, 498), "RAG + episodic memory + Critic", fill="#9eb2c8", font=small)
        frames.append(image)
    frames[0].save(output, save_all=True, append_images=frames[1:], duration=700, loop=0, optimize=True)


if __name__ == "__main__":
    main()
