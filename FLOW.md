# How you get access to a repo, and why it is safe

## The flow in five steps

1. **You request access.** Open an issue in this repo with the form "Request team access".
   Pick a team and write one line about why. You are logged in with your GitHub user, so we know who you are.
   Under "Who" you are preselected. Pick more people from the list to request on behalf of colleagues in the same request.

2. **A pull request is created automatically.** A script adds your name to `access.yaml` and opens a PR.
   The file is the list of who should have access to what. You get a comment on the issue with a link.

3. **The plan is shown.** A comment on the PR shows exactly what will happen in GitHub,
   for example "team Kunde B: add <you> (member)". Nothing beyond what is listed there is done.

4. **Someone in the platform team approves.** They look at the plan, approve, and the PR is merged.
   If in doubt, they ask you in the PR.

5. **Access updates by itself.** Once the PR is merged, a job runs that makes the change in GitHub
   and checks that the result matches the file. You get a ✅ on the PR, and the issue is closed. From then on you have access.

Usually it takes from minutes to a few hours, depending on when someone in platform sees the PR.

## Why this is safe

**One file is the source of truth.** `access.yaml` describes all access. Everything done in GitHub follows from what is written there,
and the git history shows who changed what, when, and who approved.

**Nobody can grant themselves access.** You can request, but not approve. Only the platform team can approve, and the rules
on `main` require one of them to do it. This also applies to org owners, who cannot bypass the rule.

**Four eyes before anything happens.** The requester and the approver are always two different people.
A compromised account can therefore propose access, but not get it.

**The job that changes access has a short-lived key card.** It uses a GitHub App that creates a token that
only works for one hour and only exists inside the run. There is no permanent key to steal.

**Big changes stop automatically.** Changing owners, the base setting for the whole org, or deleting
teams is not carried out on its own, even if the PR is merged. An owner must then confirm explicitly.

**Everything is verified afterwards.** After every run the whole org is read again and compared with the file.
If it does not match, the job fails and an owner is notified. The report of all access is stored for every run.

**You see everything.** Everyone in the org has read access to this repo. You can see at any time who has access to what,
and who approved it.

## Frequently asked questions

**I need access now.** Submit the form and give someone in the platform team a nudge. From approval to access it takes under two minutes.
Access granted directly in the GitHub UI, outside the file, is removed on the next run.

**I am switching projects.** Submit two requests: "Remove" from the old team and "Add" to the new one.

**Why can I read all repos?** All developers have read access to everything, so they can learn from and reuse code.
It is write and admin access that is managed per customer. Your team has admin on the customer's repos, so you can set
secrets and variables yourself. Deleting repos and changing visibility is blocked at org level.
