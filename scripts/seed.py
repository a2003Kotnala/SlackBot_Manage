from textwrap import dedent


def main() -> None:
    sample = dedent(
        """
        Weekly delivery huddle for the FollowThru launch.
        We aligned on shipping the FollowThru Slack rollout this sprint and
        demoing the production workflow to leadership next week.
        Decision: Use PostgreSQL as the source of truth for workflow state.
        Action: Finalize the FollowThru preview API contract @anita 2026-03-21
        Action: Validate app mentions and slash commands in production @ravi 2026-03-22
        Risk: Slack workspace permissions for canvases may delay workspace rollout.
        Question: Do we need approval before enabling FollowThru in all delivery channels?
        """
    ).strip()
    print(sample)


if __name__ == "__main__":
    main()
