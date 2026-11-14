// Files a nightly-failure issue -- once.
//
// Every job of stress-tests.yml used to call issues.create on each red night, so a
// failure that persisted for two months left 56 identical "Nightly memory profiling
// run failed" issues behind (#576-#679), each one hiding the others. Now the first
// red night opens the issue and every later one comments on it, so the issue's
// timeline is the history of the failure and closing it means something.
//
// Called from actions/github-script after actions/checkout:
//   const fileNightlyIssue = require('./.github/scripts/file_nightly_issue.js');
//   await fileNightlyIssue({ github, context, core, title, body, labels });

module.exports = async function fileNightlyIssue({ github, context, core, title, body, labels }) {
  const { owner, repo } = context.repo;

  // labels[0] narrows the listing; the exact title is what identifies the issue.
  const open = await github.paginate(github.rest.issues.listForRepo, {
    owner,
    repo,
    state: 'open',
    labels: labels[0],
    per_page: 100,
  });
  const existing = open.find((issue) => !issue.pull_request && issue.title === title);

  if (existing) {
    await github.rest.issues.createComment({
      owner,
      repo,
      issue_number: existing.number,
      body: `Failed again.\n\n${body}`,
    });
    core.info(`Commented on open issue #${existing.number} instead of opening a duplicate.`);
    return existing.number;
  }

  const created = await github.rest.issues.create({ owner, repo, title, body, labels, assignees: [] });
  core.info(`Opened issue #${created.data.number}.`);
  return created.data.number;
};
