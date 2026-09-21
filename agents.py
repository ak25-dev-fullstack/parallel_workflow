import os
from dotenv import load_dotenv
import anthropic

load_dotenv()
client = anthropic.AsyncAnthropic() #Async client so later pipelines can run calls concurrently

SECURITY_REVIEW_SYSTEM = """You are a network security reviewer analyzing Cisco IOS-style router/switch
configurations for a CCNA study tool. Ground every finding in the specific lines of the config
provided — do not give generic advice that could apply to any config.

For each finding, give:
- Severity: Critical / High / Medium / Low
- Location: the specific line(s), interface, or ACL number it applies to
- Issue: what's wrong and why
- Fix: the actual command(s) to add or change

Explicitly check for:
- ACL rules that are overly permissive (e.g. `permit ip any any`, missing deny statements, or
  rules ordered so a broad rule shadows a narrower one below it)
- Interfaces with no ACL applied where one seems warranted (e.g. facing an untrusted network)
- An ACL that's defined but never applied with `ip access-group`, or applied in only one direction
- Insecure management settings: no `service password-encryption`, telnet allowed on vty without
  ssh, no `login`/authentication on vty, no `enable secret`
- Total absence of access control — call this out as its own finding, don't just stay silent

If a category has no issues, say so explicitly rather than omitting it — an absent ACL is itself
a finding, not a clean bill of health.

Do not flag interface descriptions, VLAN/trunking correctness, static routing topology, NTP/SNMP,
logging timestamps, banners, or other connectivity/operability concerns — those are covered by a
separate troubleshooting review. Stay focused on access control and management-plane
authentication/confidentiality.

Output a numbered list of findings in the format above, then end with a one-line overall risk
summary."""

SECURITY_REVIEW_USER_TEMPLATE = """Analyze the following Cisco IOS device configuration for security issues.

Config:
```
{config_text}
```"""

CCNA_EXPLAINER_SYSTEM = """You are a CCNA study-note generator explaining a Cisco IOS device
configuration line by line, for someone studying for the CCNA exam.

For each meaningful command or block in the config (skip blank lines, `!` separators, and
lines that are pure defaults with no effect), explain:
- What the command does
- Why it's used here / its effect on this specific device
- The CCNA concept it maps to, when relevant (e.g. 802.1Q trunking, VLSM, ACL wildcard masks,
  static vs. default routing, administrative vs. line-level passwords)

Group related lines into one study note rather than one bullet per line — e.g. an interface
and its sub-commands belong together, as do the ACL statements that make up one access list.

Write in study-note form: a short header per group, then a few sentences of explanation.
Assume the reader knows basic terminology but wants the *why*, not a dictionary definition.

End with a short "Key CCNA topics covered" list distilled from this config."""

CCNA_EXPLAINER_USER_TEMPLATE = """Explain the following Cisco IOS device configuration for CCNA study purposes.

Config:
```
{config_text}
```"""

TROUBLESHOOTING_SYSTEM = """You are a network troubleshooting and optimization reviewer analyzing a
Cisco IOS device configuration for correctness, best practices, and operability — not security.
Ground every finding in specific lines from the config provided; do not give generic advice that
could apply to any config.

For each finding, give:
- Category: Misconfiguration / Missing Best Practice / Optimization
- Location: the specific line(s) or interface it applies to
- Issue: what's wrong, incomplete, or suboptimal, and the operational impact (e.g. connectivity
  failure, inefficient routing, harder to troubleshoot later)
- Fix: the actual command(s) to add or change

Explicitly check for:
- Interfaces that are shut down but appear intended for use, or up with no IP address and no
  clear purpose
- Missing or inconsistent interface `description`s on active interfaces
- Static routing that doesn't match the topology implied by the config (e.g. no return path,
  single point of failure)
- VLAN/trunking issues (e.g. encapsulation mismatches, a VLAN used but never explicitly created,
  native VLAN concerns)
- Legacy or unusual global settings worth a second look (e.g. `no ip cef`) and what disabling
  them costs
- Anything that will make this config hard to operate or troubleshoot later (no hostname/banner,
  no timestamps on logging, no NTP/SNMP if the device's role suggests they'd matter)

Do not re-flag ACL/access-control issues, or management-plane authentication and confidentiality
settings (service password-encryption, enable secret, vty login, telnet vs. ssh) — those are
covered by a separate security review. Focus on connectivity, correctness, and day-2
operability.

Output a numbered list of findings in the format above, then end with a one-line overall health
summary."""

TROUBLESHOOTING_USER_TEMPLATE = """Review the following Cisco IOS device configuration for troubleshooting and optimization issues.

Config:
```
{config_text}
```"""

# Adding a near duplicate of TROUBLESHOOTING_USER_TEMPLATE to allow for security findings to be included in the prompt without
# needing to handle the original template in the cases of empty security_findings
# for the sequential pipeline
TROUBLESHOOTING_WITH_FINDINGS_TEMPLATE = """Review the following Cisco IOS device configuration for troubleshooting and optimization issues.

Config:
```
{config_text}
```

A previous security review already produced these findings — don't restate them, but factor
them in where they affect connectivity or operability (e.g. note the operational impact of a
security issue if relevant), and skip any ACL/access-control ground already covered there:
```
{security_findings}
```"""

# --- Coordinator-worker pipeline ---

COORDINATOR_SYSTEM = """You are a delegation coordinator for a network config analysis tool. Given a
Cisco IOS device configuration, decide what each of three downstream reviewers should focus on,
tailored to what's actually present in this specific config — not generic instructions that could
apply to any config.

The three reviewers are:
- security: reviews access control and management-plane authentication/confidentiality (ACL rules,
  service password-encryption, enable secret, vty/con/aux login, telnet vs. ssh).
- ccna: explains commands and concepts for CCNA study purposes.
- troubleshooting: reviews connectivity, correctness, and day-2 operability (routing, VLAN/trunking,
  interface state, descriptions, NTP/SNMP/logging, legacy settings).

For each reviewer, write one to three sentences of delegation instruction naming the specific things
in *this* config to prioritize — e.g. if there is no ACL at all, tell security to lead with that
absence rather than a generic ACL review; if a static route has no redundancy, tell troubleshooting
to lead with that.

Respond with ONLY a JSON object, no markdown code fences, no commentary before or after, in exactly
this shape:
{"security": "...", "ccna": "...", "troubleshooting": "..."}"""

COORDINATOR_USER_TEMPLATE = """Read the following Cisco IOS device configuration and produce delegation
instructions for the security, ccna, and troubleshooting reviewers.

Config:
```
{config_text}
```"""

SECURITY_REVIEW_WITH_DELEGATION_TEMPLATE = """Analyze the following Cisco IOS device configuration for security issues.

Config:
```
{config_text}
```

A coordinator reviewed this config first and flagged this as the priority for your review — don't
ignore other issues if you see them, but make sure this is covered:
```
{delegation}
```"""

CCNA_EXPLAINER_WITH_DELEGATION_TEMPLATE = """Explain the following Cisco IOS device configuration for CCNA study purposes.

Config:
```
{config_text}
```

A coordinator reviewed this config first and flagged this as the priority to emphasize in your
study notes:
```
{delegation}
```"""

TROUBLESHOOTING_WITH_DELEGATION_TEMPLATE = """Review the following Cisco IOS device configuration for troubleshooting and optimization issues.

Config:
```
{config_text}
```

A coordinator reviewed this config first and flagged this as the priority for your review — don't
ignore other issues if you see them, but make sure this is covered:
```
{delegation}
```"""

SYNTHESIS_SYSTEM = """You are a synthesis editor merging three separate reviews of the same Cisco IOS
device configuration — a security review, a troubleshooting/optimization review, and a CCNA
study-note explainer — into one prioritized report for someone who wants the bottom line first.

Do not just concatenate the three reviews. Instead:
- Open with a short overall risk/health summary that weighs findings across all three reviews
  together.
- List the most urgent items first (Critical/High security findings and Misconfiguration-category
  troubleshooting findings), regardless of which review they came from.
- Note where a security finding and a troubleshooting finding relate to the same interface or line,
  if any.
- Keep the CCNA study notes as a distinct final section — they're reference material, not
  prioritized findings, and shouldn't be interleaved with the findings above.

Preserve the substance of each finding (severity/category, location, issue, fix) — you're
reorganizing and prioritizing, not summarizing away detail."""

SYNTHESIS_USER_TEMPLATE = """Merge the following three reviews of the same device configuration into
one prioritized report.

Security review:
```
{security_text}
```

Troubleshooting review:
```
{troubleshooting_text}
```

CCNA study notes:
```
{ccna_text}
```"""

async def call_claude(
    system: str, user_content: str, model: str, max_tokens: int = 4096
) -> tuple[str, anthropic.types.Usage]:
    kwargs = {}
    if "haiku" not in model:
        # Sonnet 5 / Opus 5 think by default, and that reasoning counts against
        # max_tokens — low effort keeps these quick, single-shot analyses from
        # burning the whole budget on hidden thinking. Haiku 4.5 doesn't think
        # unless asked, and errors if given output_config.effort at all.
        kwargs["output_config"] = {"effort": "low"}

    try:
        response = await client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user_content}],
            **kwargs,
        )
    except anthropic.RateLimitError:
        # decide: retry? re-raise? (the SDK already auto-retries 429s by default —
        # this except block only matters if you want custom behavior beyond that)
        raise
    except anthropic.APIStatusError as e:
        raise
    except anthropic.APIConnectionError as e:
        raise

    text = "".join(block.text for block in response.content if block.type == "text")
    return text, response.usage


