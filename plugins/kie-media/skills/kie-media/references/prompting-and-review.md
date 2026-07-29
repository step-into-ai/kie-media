# Prompting and review

## Prompt construction

- Image: subject + setting + composition + lighting + style + fidelity constraints.
- Image edit: describe the change, not the full existing scene.
- Image-to-video: describe camera and subject motion; do not redescribe the frame.
- Prefer positive qualities (`tack sharp`, `stable geometry`) over long negative lists.
- Keep prompts concise; the planner caps generated prompts at 180 words.
- Product references are authoritative for shape, packaging, colors and label layout.
- Never invent product claims, certifications, ratings, prices, awards, studies or endorsements.

## Visual QA rubric

Score each candidate for:

1. brief and format fidelity
2. reference/product identity
3. composition and negative space
4. typography and factual correctness
5. anatomy, geometry and video temporal stability
6. unwanted logos, pseudo-text, artifacts or watermarks
7. consistency with the rest of the set

For a defect, identify its cause and change one prompt/parameter dimension. Resubmit only the failed stage. Do not duplicate an in-flight task and do not regenerate every candidate blindly.
