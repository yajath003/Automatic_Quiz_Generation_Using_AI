import csv
from app import create_app
from app.models import GeneratedQuestion

app = create_app()

with app.app_context():
    questions = GeneratedQuestion.query.all()

    with open("generated_quiz.csv", "w", newline='', encoding="utf-8") as file:
        writer = csv.writer(file)

        # REQUIRED HEADER (DO NOT CHANGE)
        writer.writerow(["question", "option_a", "option_b", "option_c", "option_d", "answer"])

        for q in questions:
            options = q.options if q.options else []

            # Ensure 4 options
            if len(options) < 4:
                continue

            opt_a, opt_b, opt_c, opt_d = options[:4]

            # Convert correct answer → A/B/C/D
            correct = "A"  # default

            if q.correct_answer == opt_a:
                correct = "A"
            elif q.correct_answer == opt_b:
                correct = "B"
            elif q.correct_answer == opt_c:
                correct = "C"
            elif q.correct_answer == opt_d:
                correct = "D"

            writer.writerow([
                q.question_text,
                opt_a,
                opt_b,
                opt_c,
                opt_d,
                correct
            ])

    print("✅ CSV generated: generated_quiz.csv")