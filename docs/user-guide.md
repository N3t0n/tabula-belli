# User guide

Tabula Belli lets you discover, organize, and join tabletop gaming events across Europe. This guide covers the published portfolio application and the same workflows in a local installation.

**[Open the application](https://tabula-belli.n3t0n.com/)** · [Project overview](../README.md) · [Local installation](installation.md)

The supplied events, registrations, and player profiles are fictional. Locations and games are real reference information. This is a demonstration, not a platform for booking real activities.

## 1. Choose how to try the application

| Access | What you can do |
| --- | --- |
| Without an account | Browse, search and filter events; view event and game details. |
| Shared demo account | Explore signed-in workflows, create and manage events under the shared identity, and join or cancel registrations. Profile and account changes are protected. |
| Your own verified account | Use event workflows and manage your own profile, email, password, and account deletion. |

For the demo, open **Log in**, select **Fill demo credentials**, then select **Sign in**:

- Username: `horus_lupercal`
- Password: `TestPass123!`

All demo visitors use the same account and see the same activity. An event owned by that account can therefore be managed by another demo visitor. Other seed profiles exist to populate the demonstration; their names are not alternative login credentials.

The published dataset is rebuilt every two months. Visitor accounts, events, and registrations are removed as part of that reset. Do not rely on the portfolio application to preserve your content.

## 2. Browse and find events

1. Open **Events** from the main navigation.
2. Search by text and narrow the list using game, category, event type, status, or location filters.
3. Select a country and, where applicable, a region and city. Available location choices depend on the selected area.
4. Use sorting and pagination to explore the results.
5. Open an event to view its description, game, dates, location, capacity, registration availability, and organizer contact information.

The event list defaults to **Upcoming**. Choose **All** to include other event states, including canceled events. **Completed** shows ended events marked completed or canceled. A game detail page provides a listing of related events.

Locations come from the included European catalogue; it is not a list of every settlement. A venue's name and street address are separate from its selected city.

Use the theme control in the navigation to switch between light and dark appearance.

## 3. Create and verify your own account

1. Sign out if you are using the demo.
2. Select **Sign Up** and enter a username, email address, and password with confirmation.
3. Submit the form and follow the instructions on **Check your inbox**.
4. Open the Tabula Belli verification email, follow its link, and select **Confirm my email**.
5. Sign in using your username or email and password.

On the published application, use an email address you can access. Check your spam folder if the message does not appear. If necessary, try signing in again to request another verification message.

In a local development installation, emails are printed in the Django server terminal rather than delivered. Open the link from that output; see the [Installation guide](installation.md).

Verified email is required for event participation and management. The demo identity is already verified.

## 4. Join an event

Open the event's detail page while signed in with a verified account. If registration is available, use its registration control and check the resulting registered state and participant count.

Registration availability is separate from the event's overall status:

| Registration state | Meaning |
| --- | --- |
| Open | Registration is available and capacity remains. |
| Not open yet | The registration opening time has not arrived. |
| Closed | The registration deadline has passed or the event has started. |
| Full | All available places are taken. |
| Canceled | The event was canceled. |

You cannot hold duplicate confirmed registrations for the same event. Availability is checked when you submit: another visitor may take the last place after you open the page.

To cancel your place, use the cancellation control on the event detail page or the corresponding action in **My Events**. Ordinary registration cancellation is available before the event starts while the event is active. Cancellation frees the place and removes the event from your confirmed registrations view; it does not delete the event.

## 5. Create an event

1. Open **My Events** and select **Create Event**.
2. Choose the game and event type.
3. Enter a title and description.
4. Select the country, region where applicable, and city; enter the venue information.
5. Set the start and end date/time, capacity, and any optional price.
6. Review the registration window and organizer contact email.
7. Select **Create Event** and find the event in your organizing list.

Important form rules:

- A newly created event must start at least 24 hours in the future. For a quick test, choose a date at least two days ahead.
- The event must end after it starts.
- Capacity must be between 1 and 10,000.
- When both registration dates are supplied, opening must precede closing; closing must precede the event start.
- If both registration dates are left empty, registration opens at creation and closes 24 hours before the event starts.
- Event date/time inputs use the application's Europe/Berlin timezone, including its daylight-saving changes.
- An organizer contact email is required. It is initially filled from your account but can be changed; this address is visible on the event detail page.

The price field describes the event; the application does not process payments. Form errors explain which values need correction.

## 6. Manage events and participants

Use **My Events → Organizing** to find events owned by your account. Open their details or use the available management actions.

**Editing:** select **Edit**, change the fields, and submit **Update Event**. Editing is available only while an event is active and has not started. Completed and canceled events cannot be reopened through this flow.

**Canceling an event:** use **Cancel** or **Cancel Event** and confirm. This marks the event as canceled and cancels its confirmed registrations. The event remains in the history; cancellation is not physical deletion and cannot be undone through the interface.

**Participants:** on an event you manage, expand **Participants List** to inspect confirmed participants and their email addresses. Use the removal action while the event remains editable to cancel a participant's registration and free their place.

Regular users manage only events owned by their account. The shared demo follows the same rule, but all demo visitors share that ownership. An organizer can see participant email addresses for their events; the organizer's contact address is visible to event viewers.

## 7. Use My Events

The dashboard separates:

- **Organizing:** events owned by your account, including their history.
- **Registrations:** events you have registered for, including canceled registrations. Each event appears once, even if you cancel and later register again.

Both tabs offer **All**, **Active**, **Completed**, and **Canceled**. Organizing filters the event's status. Registrations filters your participation: Active and Completed require a confirmed registration in an active or completed event; Canceled includes withdrawn registrations, registrations removed by the organizer, and canceled events. The row distinguishes **Registration canceled** from **Event canceled** without claiming who canceled a registration. Completed describes the event's status, not proof of attendance.

Canceling a registration keeps it in All and Canceled. If the event later completes, your withdrawn registration stays in Canceled. Registering again, when available, returns it to Active without duplicating the event.

Search by event title or game and use pagination. Tab counts show the total events in each section; the table shows the filtered result count. Changing a filter or submitting a search starts at the first page. Switching tabs clears the search and returns to All. Canceling a registration preserves the current search and filter and adjusts the page if needed; canceling an organized event returns to Organizing/All.

Event statuses are **Active**, **Completed**, and **Canceled**. Active does not necessarily mean registration is open. On the published application, a scheduled task marks ended active events as completed every five minutes; a short delay is possible. Local evaluation uses the maintenance command described in the installation guide.

## 8. Manage your profile and account

Open your profile from the account navigation. Your own account can edit its username, optional first/last name, location, and favorite games.

Use **Email Settings** and **Password Settings** for their dedicated account flows. A new email address must be verified through the confirmation process. Read the form's instructions and messages before completing changes.

If you forget your password, select **Forgot password?** on the login page. Follow the reset email link, enter the new password twice, and sign in with it. Development installations show the email in the server terminal.

The shared demo's profile, email, password, password recovery, and deletion are restricted. Create your own account to try those changes.

## 9. Delete your account

For your own non-administrator account, open your profile and select **Delete Account**. Review the consequences before submitting the final confirmation.

- Your future active organized events are canceled, together with their confirmed participants' registrations.
- Your confirmed participation in current or upcoming active events is canceled.
- Past events and participation records remain with **Deleted account** in place of your identity and without a link to your account.
- Your organizer contact email is removed from events you owned.
- Your profile and account credentials are deleted, and you are signed out.

If an event you organize is currently in progress, deletion is blocked until it ends. The shared demo and superuser accounts cannot be deleted through this interface.

The confirmation screen combines pending cancellations and account deletion into one action. If relevant records change while you review it, the application asks you to review again. You can choose **Keep my account** instead.

Account deletion is permanent. It does not automatically remove personal information written into event titles, descriptions or venue addresses; use Contact if such text needs removal. Retained event history is still part of the disposable portfolio dataset and will be replaced by the next scheduled demo reset.

## 10. Contact and maintenance

Use **Contact** for project feedback or technical questions. Enter your email, subject, and message, then submit. This contact flow uses Formspree and is separate from account verification and recovery emails. In a local installation without a Formspree endpoint, sending is disabled.

Successful contact submissions clear the fields and show a confirmation inside the application. If sending fails, the entered data is kept and an error message is shown. The submit button is disabled while sending.

During a scheduled demo reset, the published application displays a temporary maintenance page. Wait and retry after maintenance; the dataset will have been rebuilt, and a visitor account created before the reset will no longer exist.

If an action fails, read its message first. Check that you are signed in and verified, that you own the event if you are managing it, and that its timing and registration state allow the action.
