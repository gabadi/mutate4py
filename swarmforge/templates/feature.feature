Feature: <feature name>

  # TRACKING: <issue reference>
  # Ask: does this work trace to a tracked issue or story?
  #      Use the project's issue tracking format (e.g. #N for GitHub).
  #
  # CONTRACT:
  # Ask: what are ALL inputs — path params, query params, request body, auth?
  #      What are ALL response shapes and status codes, including every error?
  #      Are any fields explicitly NOT in the response that callers might assume exist?
  #      What semantic distinctions matter (e.g. empty result vs upstream failure)?
  # Format:
  #   <METHOD> <path>
  #   request:  <param> — <type>, <constraints>
  #   response <status>: { field: type, ... } — <when>
  #   response <status>: { error: string } — <when>
  #
  # CONSTRAINTS:
  # Ask: is there a dataset scope bound — full set required, not just page 1?
  #      Are there fields unavailable from this source that callers might expect?
  #      Are there input validation rules — required fields, formats, min/max?
  #      Are there exclusion rules — filters applied at the source before results are returned?
  # Format:
  #   - <bound, exclusion, or unavailable field>
  #
  # SEQUENCING: none
  # Ask: are there operations that must run in a specific order?
  #      Are there async dependencies — must A complete before B begins?
  # Format (if not none):
  #   - <A> must complete before <B>
  #
  # NFR:
  # Ask: are there latency or throughput targets?
  #      Must this operation be idempotent — what is the key and expiry window?
  #      What must the caller display during the in-flight state (loading, disabled trigger)?
  #      How must errors be distinguishable from empty or success responses?
  # Format:
  #   - <target or requirement>
  #
  # SIDE EFFECTS: none
  # Ask: does this feature add, remove, or change any public-facing contract?
  #      (routes, events, schemas, capability registries, discovery endpoints)
  #      Does it require regenerating any derived artifact?
  #      Check the project rules for the specific delivery obligations that apply.
  # Format:
  #   - <what must be updated>
  #
  # SCOPE:
  # Ask: transfer fog exclusions from the frontier brief as `Does NOT:` entries.
  #      What is this feature explicitly NOT doing that callers might assume?
  #      What assumptions were made that are not stated in the requirements?
  # Format:
  #   - Does NOT: <exclusion>
  #   - ASSUMED: <assumption — flag if uncertain>
  #
  # UX INTENT: none
  # Design artifacts: none
  # Ask: does the project have DESIGN.md, EXPERIENCE.md, or mockup/wireframe files?
  #      Check project root and common locations (docs/, design/, assets/).
  #      List found paths here so the UX Engineer can load them.
  # Ask: does this feature have user-visible rendering, layout, or interaction behaviour?
  #      If yes, author all four dimensions below as concrete observable statements.
  #      Omit if the feature has no UX requirements — absence tells the UX Engineer to skip.
  # Visual Composition: how elements are spatially arranged and visually distinguished
  # Information Hierarchy: what is prominent, secondary, or hidden; reading order
  # Interaction Feel: responsiveness, affordances, feedback on user actions
  # State Transitions: what changes between states (loading, empty, error, success)
  # Format:
  #   Visual Composition: <observable statement>
  #   Information Hierarchy: <observable statement>
  #   Interaction Feel: <observable statement>
  #   State Transitions: <observable statement>

  # <feature-slug>-1
  Scenario Outline: <description>
    Given <precondition>
    When <action>
    Then <expected outcome>

    Examples:
      | <param> | <param> |
      | <value> | <value> |
