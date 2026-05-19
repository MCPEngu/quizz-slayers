import os
import random

from playwright.sync_api import Page

LOGIN_URL = "https://edux.cmcu.edu.vn/login"


def test_wait_for_user_login(page: Page) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    print("\n[INFO] Please log in in the opened browser.")
    print("[INFO] After you reach the quiz screen, press Enter here to click 'Tra loi cau hoi'.\n")
    input()

    wrong_answers: dict[str, set[str]] = {}

    while not page.is_closed():
        no_question_button = page.get_by_role("button", name="Không có câu hỏi")
        if no_question_button.is_visible():
            next_page_button = page.get_by_role("button", name="Trang sau")
            next_page_button.click()
            print("[INFO] No question on this slide. Clicked 'Trang sau'.")
            page.wait_for_timeout(500)
            continue

        question = page.locator("p.my-3.text-gray-800.leading-relaxed").first
        if not question.is_visible():
            page.get_by_role("button", name="Trả lời câu hỏi").click()
            question.wait_for(state="visible")
        question_text = question.inner_text().strip()
        print(f"[INFO] Question: {question_text}")

        answers = page.locator(
            "div.flex.items-center.space-x-6.p-8.rounded-xl.border-2.transition-colors.cursor-pointer.min-h-\\[80px\\]"
        )
        answer_count = answers.count()
        print(f"[INFO] Answers found: {answer_count}")

        answer_texts: list[str] = []
        for i in range(answer_count):
            block = answers.nth(i)
            letter = block.locator("span.font-bold").first.inner_text().strip()
            text = block.locator("div.prose p").first.inner_text().strip()
            full_text = f"{letter} {text}"
            answer_texts.append(full_text)
            print(f"[INFO] Answer {i + 1}: {full_text}")

        target_answer = os.environ.get("AUTO_ANSWER_TEXT", "").strip()
        clicked_answer = False
        chosen_answer_text = ""
        if target_answer:
            print(f"[INFO] Auto-answer target: {target_answer}")
            match = answers.filter(has_text=target_answer).first
            match.click()
            clicked_answer = True
            chosen_answer_text = target_answer
        elif answer_count > 0:
            tried_for_question = wrong_answers.get(question_text, set())
            available_indices = [
                i for i, text in enumerate(answer_texts) if text not in tried_for_question
            ]
            if not available_indices:
                tried_for_question.clear()
                available_indices = list(range(answer_count))

            random_index = random.choice(available_indices)
            chosen_answer_text = answer_texts[random_index]
            print(f"[INFO] AUTO_ANSWER_TEXT not set. Random pick: {chosen_answer_text}")
            answers.nth(random_index).click()
            clicked_answer = True
        else:
            print("[WARN] No answers available to click.")

        if clicked_answer:
            page.get_by_role("button", name="Kiểm tra").click()
            print("[INFO] Clicked 'Kiem tra' button.")

            next_button = page.get_by_role("button", name="Câu tiếp theo")
            retry_button = page.get_by_role("button", name="Thử lại")
            next_page_button = page.get_by_role("button", name="Trang sau")

            for _ in range(40):
                if next_page_button.is_visible():
                    next_page_button.click()
                    print("[INFO] Clicked 'Trang sau' button.")
                    break
                if next_button.is_visible():
                    next_button.click()
                    print("[INFO] Clicked 'Cau tiep theo' button.")
                    break
                if retry_button.is_visible():
                    retry_button.click()
                    if chosen_answer_text:
                        wrong_answers.setdefault(question_text, set()).add(chosen_answer_text)
                        print(f"[INFO] Marked wrong answer: {chosen_answer_text}")
                    print("[INFO] Clicked 'Thu lai' button.")
                    break
                page.wait_for_timeout(250)
            else:
                print("[WARN] No follow-up button appeared.")

        page.wait_for_timeout(500)

    # Keep this test non-failing while we are still wiring selectors.
    print(f"[INFO] Current URL after click: {page.url}")
    print("[INFO] Browser will stay open. Close the browser window to finish.")
    page.wait_for_event("close")
