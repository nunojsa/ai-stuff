# ai-stuff

My set of AI ramblings — a collection of skills and tools for use with
AI coding agents.

## Skills

| Skill | Description |
|-------|-------------|
| [git-rewrite-commits](skills/git-rewrite-commits/SKILL.md) | Interactively rewrite git commit messages for a range of commits |
| [gh-iterate](skills/gh-iterate/SKILL.md) | Iterate on a GitHub PR by addressing review feedback as fixup commits |
| [web-search](skills/web-search/SKILL.md) | Fetch any URL as clean markdown, or search the web via a local SearXNG instance |

## Setup

These skills follow the [Agent Skills](https://agentskills.io/specification)
standard and should work with both [pi](https://github.com/mariozechner/pi-coding-agent)
and [Claude Code](https://docs.anthropic.com/en/docs/claude-code) and potentially other agents (Just focused on these ones).

Clone the repository:

```bash
git clone https://github.com/nunojsa/ai-stuff.git ~/work/ai-stuff
```

### Claude Code

Symlink each skill into Claude's global skills directory:

```bash
mkdir -p ~/.claude/skills
ln -s ~/work/ai-stuff/skills/<skill-name> ~/.claude/skills/<skill-name>
```

Claude Code will pick up the skill on the next session.

### pi

Symlink each skill into pi's global skills directory:

```bash
ln -s ~/work/ai-stuff/skills/<skill-name> ~/.pi/agent/skills/<skill-name>
```

Alternatively, if you've already set up the skills for Claude Code, pi can
discover them directly. Add the Claude skills directory to your pi
`settings.json`:

```json
{
  "skills": ["~/.claude/skills"]
}
```

This way a single set of symlinks serves both agents.

## License

This project is licensed under the [GPLv2](LICENSE).
