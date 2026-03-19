from textwrap import dedent


def main() -> None:
    sample = dedent(
        """
        Weekly delivery huddle for the ZManage pilot.
        We aligned on shipping the Slack command MVP this sprint and demoing it
        to leadership next week.
        Decision: Use PostgreSQL as the source of truth for workflow state.
        Action: Finalize the preview API contract @anita 2026-03-21
        Action: Add initial Alembic migration @ravi 2026-03-22
        Risk: Slack workspace permissions for canvases may delay production rollout.
        Question: Do we need approval before enabling the bot in all delivery channels?
        """
    ).strip()
    print(sample)


if __name__ == "__main__":
    main()
