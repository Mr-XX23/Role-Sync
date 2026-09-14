"""Skills: playbooks the agent follows for recurring sales jobs (decided 2026-09-14).

- Built-in skills ship with the code (``builtin/*.md``); a workspace's owners and admins can customize one.
- Owners and admins write skills for the whole workspace; any member except viewers writes private ones.
- Each rep switches skills on or off for their own agent; admins can switch a skill off for everyone.
- The agent sees its switched-on skills as a short list, loads one with ``use_skill`` when a request
  matches (or the rep picked it), and can hand one to a sub-agent. Skills guide the work but never add
  tools or skip approvals.
"""
