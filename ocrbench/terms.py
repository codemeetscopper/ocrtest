"""Shared user-facing definitions for the dashboard and exported reports."""
import html

TERMS = [
    ('Engine / device', 'OCR is optical character recognition: reading text from images. Engine identifies the software. CPU is the computer processor; GPU is the graphics processor. Observed device reports actual execution. CUDA is NVIDIA GPU computing; ONNX may still assign some operations to CPU.', ['ENGINE / DEVICE']),
    ('Status', 'Completed means the candidate finished. Error, unavailable, timeout, or crash means it did not finish normally. Check failures and the worker log as well as this status.', ['STATUS']),
    ('Text F1', 'Higher is better. Balances precision (how many predicted regions are correct) and recall (how many expected regions were found). A correct match requires sufficient polygon overlap and exactly matching text. Requires reviewed, complete ground truth.', ['TEXT F1', 'F1']),
    ('CER · character error rate', 'Lower is better. Inserted, deleted, and substituted characters divided by reference characters. Case, spaces, punctuation, and Unicode differences count. Can exceed 100%; requires reviewed, complete ground truth.', ['CER']),
    ('P95 latency · milliseconds', 'Lower is better. 95% of successful measured image-to-result calls were at or below this time. Includes image preparation, OCR, communication, and scoring. Excludes initialization, first result, warmups, and final record saving. Five calls give only a rough estimate.', ['P95 LATENCY', 'P95 MS', 'MAXIMUM P95 MS']),
    ('Completed FPS · frames per second', 'Higher is better. Successfully completed frames divided by measurement-loop wall time, including scheduling, failed attempts, and record saving. This is throughput, not camera sensor FPS or the inverse of P95.', ['COMPLETED FPS', 'FPS']),
    ('Peak RAM · megabytes', 'Highest sampled resident memory of the worker and its child processes combined. Excludes the dashboard and GPU memory; shared memory can be counted more than once. Smaller values use less host memory.', ['PEAK RAM', 'RAM MB']),
    ('Failures', 'Measured attempts that did not succeed, including frames not attempted after a fatal worker failure. Initialization errors may have no measured attempts and appear as an unavailable status instead.', ['FAILURES']),
    ('Confidence', 'Recognition confidence reported by the engine, shown as a percentage. It is not a verified probability of correctness and is not calibrated across engines. A dash means the engine supplied no comparable confidence.', ['CONFIDENCE']),
    ('Source position · X, Y', 'Polygon corners in original-image pixels. X increases to the right; Y increases downward, from the top-left origin. Upscaled or cropped predictions are mapped back to these coordinates.', ['SOURCE POSITION X Y']),
    ('IoU · intersection over union', 'Overlap area of a predicted polygon and reference polygon divided by their combined area. The threshold decides whether locations can match; text F1 also requires exact text.', ['POLYGON IOU THRESHOLD']),
    ('Ground truth', 'Human-provided expected text and locations. Reviewed means a person checked them; complete means all visible text is covered. Draft or partial annotations cannot produce full-image F1/CER.', ['ANNOTATIONS', 'REVIEWED', 'GROUND TRUTH']),
    ('Unavailable · —', 'No valid measurement or reference is available. This is neither zero nor a passing score. GPU utilization/VRAM and unsupported quality metrics remain unavailable.', []),
    ('Median / P99', 'Median is the middle successful call duration. P99 is the duration at or below which 99% of successful measured calls fell. Lower is faster; both exclude cold start and warmups.', ['WARM MEDIAN P99']),
    ('Initialization / first result', 'Initialization covers worker startup and adapter creation. First result is time from worker start through the first real inference. Model caches may already be warm; these are separate from steady measurements.', ['WORKER INITIALIZATION', 'FIRST RESULT FROM WORKER START']),
    ('Warmups / repetitions', 'Warmups are unscored calls before timing. Repetitions are repeated measured inputs; they improve timing samples but do not add independent scene diversity.', ['WARMUP CALLS', 'REPETITIONS']),
    ('Track / preparation', 'Full-image OCR detects and reads the entire image. Known crops use annotated regions and report crop CER separately. Raw, upscale, contrast, and sharpen describe the image preparation applied.', ['TRACK', 'PREPARATION']),
    ('Queue drops / capture faults', 'Queue drops are frames skipped when the bounded inference queue is full. Capture faults are failures to acquire a frame from the camera. They are reported separately from OCR failures.', ['RECEIVED QUEUE DROPS']),
    ('Arrival / sample FPS', 'Configured replay arrival rate or camera sampling cadence. The physical camera rate and completed OCR throughput may differ. Keep latest drops older waiting frames; FIFO drops new arrivals when full.', ['ARRIVAL SAMPLE FPS']),
    ('Acceptance gates', 'Optional pass/fail limits for P95 and text F1. A missing measurement is unmeasured, not a pass. No combined score or automatic engine winner is generated.', ['ACCEPTANCE GATES', 'MINIMUM TEXT F1']),
    ('Expected / observed labels', 'Expected state says whether text should be present or absent. Observed state and evidence come from OCR. Correct/incorrect compares them; uncertain means the result cannot establish the assertion.', ['EXPECTED LABEL', 'EXPECTED STATE', 'OBSERVED', 'OUTCOME', 'EVIDENCE']),
    ('Raw text / parsed value', 'Raw text is the original OCR output inside a field region. Parsed value/unit applies the configured parser. Exact/mismatch compares against the expected string without silently correcting OCR.', ['RAW OCR TEXT', 'PARSED VALUE UNIT', 'STRICT EXPECTED MATCH', 'RECOGNIZED TEXT']),
    ('Setup / source', 'Samples and settings used by a run. Compare matching inputs, models, languages, preparation, thread counts, and annotation snapshots before interpreting differences.', ['SETUP SOURCE']),
    ('Session-only camera frames', 'Default camera images are temporary and reviewable until the app restarts. Enable Save camera frames to dataset before a run for permanent image retention. Metrics and recognized text are retained in run history.', []),
    ('Table arrows / units', '↑ means higher is generally preferable; ↓ means lower is generally preferable. The small sorting triangle indicates the active sort order. ms = milliseconds, MB = megabytes, FPS = frames per second. Different quality/speed tradeoffs still need judgement.', []),
]


def glossary():
    return [{'title': title, 'description': description, 'aliases': aliases} for title, description, aliases in TERMS]


def glossary_html():
    return '<details class="metric-guide"><summary>What do these terms mean?</summary><dl>'+''.join(
        f'<dt>{html.escape(title)}</dt><dd>{html.escape(description)}</dd>' for title, description, _ in TERMS)+'</dl></details>'
