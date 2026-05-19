import json
import os
import re
from typing import Optional

from playwright.sync_api import Page

LOGIN_URL = "https://edux.cmcu.edu.vn/login"
ENV_PATH = os.path.join(os.path.dirname(__file__), "..", ".env")
ANSWERS_PATH = os.path.join(os.path.dirname(__file__), "..", "answers.txt")
PROMPT_PATH = os.path.join(os.path.dirname(__file__), "..", "questions_prompt.txt")

QUESTION_LABEL_RE = re.compile(r"^Câu\s+(\d+)")
ANSWER_LINE_RE = re.compile(r"^(\d+)\.(.*)$")
TF_TOKEN_RE = re.compile(r"(\d+)\s*\.\s*(đúng|sai|true|false|d|đ|s|t|f|1|0)", re.IGNORECASE)


def load_env_file() -> None:
    if not os.path.exists(ENV_PATH):
        return
    with open(ENV_PATH, "r", encoding="utf-8") as env_file:
        for line in env_file:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            if key and key not in os.environ:
                os.environ[key] = value


def ensure_login_env() -> tuple[str, str]:
    load_env_file()
    email = os.environ.get("EDUX_EMAIL", "").strip()
    password = os.environ.get("EDUX_PASSWORD", "").strip()

    if not email:
        email = input("Enter EDUX email: ").strip()
    if not password:
        password = input("Enter EDUX password: ").strip()

    os.makedirs(os.path.dirname(ENV_PATH), exist_ok=True)
    with open(ENV_PATH, "w", encoding="utf-8") as env_file:
        env_file.write(f"EDUX_EMAIL={email}\n")
        env_file.write(f"EDUX_PASSWORD={password}\n")

    os.environ["EDUX_EMAIL"] = email
    os.environ["EDUX_PASSWORD"] = password
    return email, password


def load_answers() -> dict[int, str]:
    answers: dict[int, str] = {}
    with open(ANSWERS_PATH, "r", encoding="utf-8") as handle:
        for raw in handle:
            line = raw.strip()
            if not line:
                continue
            match = ANSWER_LINE_RE.match(line)
            if not match:
                continue
            index = int(match.group(1))
            answer = match.group(2).strip()
            answers[index] = answer
    return answers


def parse_question_index(text: str) -> Optional[int]:
    match = QUESTION_LABEL_RE.match(text.strip())
    if not match:
        return None
    return int(match.group(1))


def extract_options(options_locator) -> list[dict[str, str]]:
    return options_locator.evaluate_all(
        """
        nodes => nodes.map(node => {
          const letter = node.querySelector('span.flex-shrink-0')?.innerText?.trim() || '';
          const text = node.querySelector('div.prose p')?.innerText?.trim() || '';
          return { letter, text };
        })
        """
    )


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def parse_true_false_answers(answer_value: str, expected_count: int) -> list[bool]:
    normalized = normalize_text(answer_value)
    pairs = TF_TOKEN_RE.findall(normalized)
    if pairs:
        result: list[bool] = []
        for _, token in pairs:
            result.append(token in {"đúng", "d", "đ", "true", "t", "1"})
        return result

    tokens = re.findall(r"[a-zà-ỹ]+|\d", normalized)
    result = []
    for token in tokens:
        if token in {"đúng", "d", "đ", "true", "t", "1"}:
            result.append(True)
        elif token in {"sai", "s", "false", "f", "0"}:
            result.append(False)
        if len(result) >= expected_count:
            break
    return result


def test_bruteforce(page: Page) -> None:
    email, password = ensure_login_env()

    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    page.locator("#email").fill(email)
    page.locator("#password").fill(password)
    page.locator("#password").press("Enter")

    print("\n[INFO] Auto-login attempted. Finish navigation to the test.")
    print("[INFO] When ready to start, press Enter to click 'Lam bai tap' and capture payload.\n")
    input()

    start_button = page.get_by_role("button", name="Làm bài tập")
    with page.expect_response(lambda resp: "start" in resp.url, timeout=20000) as response_info:
        start_button.click()

    response = response_info.value
    payload_text = ""
    try:
        payload_json = response.json()
        payload_text = json.dumps(payload_json, ensure_ascii=False, indent=2)
    except Exception:
        payload_text = response.text()

    prompt_line = (
        "đưa ra danh sách đáp án chỉ gồm số thứ tự câu cùng phương án A,B,C,D "
        "hoặc từ khóa hoặc văn bản cần điền; với câu đúng/sai, ghi lần lượt "
        "Đúng/Sai cho từng mệnh đề; không giải thích gì thêm"
    )
    with open(PROMPT_PATH, "w", encoding="utf-8") as handle:
        handle.write(payload_text.strip() + "\n\n" + prompt_line + "\n")

    print("[INFO] Wrote questions prompt to questions_prompt.txt.")
    print("[INFO] Paste the prompt into AI, save answers into answers.txt, then press Enter to solve.\n")
    input()

    answers = load_answers()

    dialog = page.locator("div[role='dialog'][data-slot='dialog-content']")
    options_locator = dialog.locator(
        "div.relative.flex.items-center.space-x-2.p-2.border.rounded-lg.cursor-pointer"
    )
    input_locator = dialog.locator("input[type='text']")
    textarea_locator = dialog.locator("textarea")
    true_false_blocks = dialog.locator("div.border.border-gray-200.rounded-lg.p-3.bg-gray-50")
    next_button = page.get_by_role("button", name="Câu tiếp")
    submit_button = page.get_by_role("button", name="Nộp bài")

    while not page.is_closed():
        try:
            dialog.wait_for(state="visible", timeout=10000)
            label_handle = page.wait_for_function(
                """
                () => {
                  const dialog = document.querySelector("div[role='dialog'][data-slot='dialog-content']");
                  if (!dialog) return null;
                  const label = Array.from(dialog.querySelectorAll('span'))
                    .find(s => (s.textContent || '').trim().startsWith('Câu '));
                  return label ? label.textContent.trim() : null;
                }
                """,
                timeout=10000,
            )
            label_text = label_handle.json_value()
        except Exception:
            print("[WARN] Question label not visible yet. Retrying.")
            page.wait_for_timeout(200)
            continue

        question_index = parse_question_index(label_text)
        if question_index is None:
            print(f"[WARN] Could not parse question index from: {label_text}")
            page.wait_for_timeout(200)
            continue

        answer_value = answers.get(question_index, "").strip()
        if not answer_value:
            print(f"[WARN] No answer for question {question_index}. Skipping.")
        else:
            if true_false_blocks.first.is_visible():
                blocks_count = true_false_blocks.count()
                tf_answers = parse_true_false_answers(answer_value, blocks_count)
                if len(tf_answers) < blocks_count:
                    print("[WARN] Not enough true/false answers to fill.")
                else:
                    print(f"[INFO] Question {question_index}: filling true/false")
                    for i in range(blocks_count):
                        block = true_false_blocks.nth(i)
                        if tf_answers[i]:
                            block.get_by_role("button", name="Đúng").click()
                        else:
                            block.get_by_role("button", name="Sai").click()
            elif textarea_locator.is_visible():
                print(f"[INFO] Question {question_index}: filling textarea")
                textarea_locator.fill(answer_value)
            elif input_locator.is_visible():
                print(f"[INFO] Question {question_index}: filling input")
                input_locator.fill(answer_value)
            else:
                try:
                    options_locator.first.wait_for(state="visible", timeout=10000)
                except Exception:
                    print("[WARN] Options not visible yet. Retrying.")
                    page.wait_for_timeout(200)
                    continue

                print(f"[INFO] Question {question_index}: selecting {answer_value}")
                options = extract_options(options_locator)
                chosen_index = None

                if len(answer_value) == 1 and answer_value.upper() in {"A", "B", "C", "D"}:
                    target_letter = f"{answer_value.upper()}."
                    for i, option in enumerate(options):
                        if option["letter"].startswith(target_letter):
                            chosen_index = i
                            break
                else:
                    target = normalize_text(answer_value)
                    for i, option in enumerate(options):
                        option_text = normalize_text(option["text"])
                        if target and target in option_text:
                            chosen_index = i
                            break

                if chosen_index is None:
                    print("[WARN] No matching option found.")
                else:
                    options_locator.nth(chosen_index).click()

        if submit_button.is_visible():
            submit_button.click()
            print("[INFO] Clicked 'Nop bai'.")
            break

        if next_button.is_visible():
            current_label = label_text
            current_progress = dialog.evaluate(
                """
                (node) => {
                  const progress = node.querySelector('span.text-gray-700');
                  return progress ? progress.textContent.trim() : '';
                }
                """
            )
            next_button.click()
            new_label = dialog.evaluate(
                """
                (node) => {
                  const label = Array.from(node.querySelectorAll('span'))
                    .find(s => (s.textContent || '').trim().startsWith('Câu '));
                  return label ? label.textContent.trim() : '';
                }
                """
            )
            if new_label and new_label != current_label:
                continue
            try:
                page.wait_for_function(
                    """
                    (prevLabel, prevProgress) => {
                      const dialog = document.querySelector("div[role='dialog'][data-slot='dialog-content']");
                      if (!dialog) return false;
                      const label = Array.from(dialog.querySelectorAll('span'))
                        .find(s => (s.textContent || '').trim().startsWith('Câu '));
                      const progress = dialog.querySelector('span.text-gray-700');
                      const labelChanged = label && label.textContent.trim() !== prevLabel;
                      const progressChanged = progress && progress.textContent.trim() !== prevProgress;
                      return labelChanged || progressChanged;
                    }
                    """,
                    current_label,
                    current_progress,
                    timeout=10000,
                )
            except Exception:
                print("[WARN] Next question did not appear yet.")
        else:
            page.wait_for_timeout(200)

    print("[INFO] Browser will stay open. Close the browser window to finish.")
    page.wait_for_event("close")
