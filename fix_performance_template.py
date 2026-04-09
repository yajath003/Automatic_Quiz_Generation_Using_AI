import re

file_path = r"d:\yajath\Anits\project\PROJECT-A\app\templates\quiz\performance.html"

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Replace Score Cell
# Matching:
# <td>{{ "%.1f"|format(attempt.total_score) if attempt.total_score is not none else 'N/A' }}%
# </td>
score_pattern = r'<td>\{\{\s*"%\.1f"\|format\(attempt\.total_score\)\s*if\s*attempt\.total_score\s*is\s*not\s*none\s*else\s*\'N/A\'\s*\}\}%\s*\n\s*</td>'

score_replacement = """<td>
                                {% if attempt.assignment_id %}
                                    {% if attempt.assignment.results_released %}
                                        {{ "%.1f"|format(attempt.total_score) }}%
                                    {% else %}
                                        <span class="text-muted small"><i class="bi bi-lock me-1"></i>Pending</span>
                                    {% endif %}
                                {% else %}
                                    {{ "%.1f"|format(attempt.total_score) if attempt.total_score is not none else 'N/A' }}%
                                {% endif %}
                            </td>"""

# 2. Replace Action Button Cell
# Matching:
# <td>
#     <a href="{{ url_for('quiz.result', attempt_id=attempt.id) }}"
#         class="btn btn-sm btn-outline-primary">View</a>
# </td>
button_pattern = r'<td>\s*\n\s*<a\s*href="\{\{\s*url_for\(\'quiz\.result\',\s*attempt_id=attempt\.id\)\s*\}\}"\s*\n\s*class="btn\s*btn-sm\s*btn-outline-primary">View</a>\s*\n\s*</td>'

button_replacement = """<td>
                                {% if attempt.assignment_id and not attempt.assignment.results_released %}
                                <button class="btn btn-sm btn-outline-secondary" disabled title="Not released">View</button>
                                {% else %}
                                <a href="{{ url_for('quiz.result', attempt_id=attempt.id) }}" class="btn btn-sm btn-outline-primary">View</a>
                                {% endif %}
                            </td>"""

new_content = re.sub(score_pattern, score_replacement, content)
new_content = re.sub(button_pattern, button_replacement, new_content)

if new_content != content:
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("SUCCESS: Substitutions applied.")
else:
    print("FAILURE: No substitutions applied.")
    # Debug what didn't match
    if not re.search(score_pattern, content):
        print("Score pattern didn't match.")
    if not re.search(button_pattern, content):
        print("Button pattern didn't match.")
