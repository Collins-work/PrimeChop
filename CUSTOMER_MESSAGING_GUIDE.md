# Customer Messaging System Guide

## Overview
You now have a complete **Customer Messaging System** where customers can send feedback after broadcasts, and you (admin) can view, read, and reply to those messages.

---

## How It Works

### 1. **Customer Side - Sending Feedback**

When you send a broadcast using `/broadcast <message>`:
- Each customer receives the broadcast message
- A **"💬 Send Feedback"** button appears below the message
- When users click the button, they're prompted to type their message/feedback
- Their message is automatically saved to the database with their username and user ID

### 2. **Admin Side - Viewing & Replying to Messages**

#### **View All Messages**
```
/view_messages [status]
```
- **No status filter:** Shows all messages
- **Status options:** `unread`, `read`, `replied`, `all`

Example:
```
/view_messages unread     # See only unread messages
/view_messages replied    # See messages you've already replied to
/view_messages            # See everything
```

#### **View a Specific Message**
```
/view_message <message_id>
```
Shows the full details including:
- Customer name and ID
- Full message text
- Whether it's been read or replied to
- Inline buttons to send a reply or go back to the list

#### **Reply to a Customer**
1. Use `/view_message <id>` to view a specific message
2. Click the **"💬 Send Reply"** button
3. Type your reply message
4. The system automatically sends the reply to the customer

---

## Database Schema

### `customer_messages` Table
```sql
- id (BIGSERIAL PRIMARY KEY)
- user_id (BIGINT) - Customer's Telegram ID
- user_name (TEXT) - Customer's name
- message_text (TEXT) - The actual message content
- message_type (TEXT) - Type of message (e.g., 'broadcast_feedback')
- broadcast_context (TEXT) - Reference to the broadcast that triggered it
- admin_reply (TEXT) - Your reply to the customer
- admin_reply_by (BIGINT) - Your user ID (if replied)
- status (TEXT) - 'unread', 'read', or 'replied'
- created_at (TIMESTAMPTZ) - When customer sent message
- updated_at (TIMESTAMPTZ) - Last update time
```

---

## Features Implemented

### ✅ Core Features
1. **Broadcast with Feedback Button** - Every broadcast now includes a feedback button
2. **Customer Feedback Capture** - Messages are automatically saved with customer info
3. **Message List View** - See all messages with filtering by status
4. **Message Detail View** - View full message with metadata
5. **Admin Reply System** - Send direct replies to customers
6. **Automatic Notification** - Customers receive reply notifications
7. **Read Status Tracking** - Know which messages you've seen

### ✅ Database Methods (db.py)
- `add_customer_message()` - Save customer feedback
- `get_customer_messages()` - Retrieve messages with optional status filter
- `get_unread_message_count()` - Count unread messages
- `mark_message_as_read()` - Mark message as read
- `add_admin_reply()` - Save your reply
- `get_customer_message()` - Get a single message by ID

### ✅ UI Functions (ui.py)
- `format_customer_message_list()` - Display list of messages
- `format_customer_message_detail()` - Display detailed message view
- `format_broadcast_feedback_prompt()` - Prompt for customer feedback
- `format_send_reply_prompt()` - Prompt for admin reply
- `format_reply_sent_success()` - Confirmation message

---

## Usage Examples

### Example 1: Send Broadcast and Receive Feedback
```
Admin: /broadcast We have 30% off today! Order now!
      ↓
Customer sees broadcast with "💬 Send Feedback" button
Customer clicks and types: "Your app is amazing!"
      ↓
Message saved: user_id=123, message_text="Your app is amazing!", status="unread"
```

### Example 2: Admin Views and Replies
```
Admin: /view_messages unread
       ↓ Shows unread messages

Admin: /view_message 5
       ↓ Shows full message from John: "Can I get pizza delivered to my room?"

Admin clicks "💬 Send Reply"
Admin types: "Of course! We deliver to all rooms. Place your order now!"
       ↓
Message status changes to "replied"
Customer gets notification with your reply
```

### Example 3: Check Unread Count
The next broadcast will show how many new unread messages you have.

---

## Workflow Diagram

```
┌─────────────────────────────────────────────────────────┐
│  Admin sends broadcast (/broadcast)                     │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────┐
│  Each customer receives broadcast + "Feedback" button   │
└────────────────────┬────────────────────────────────────┘
                     │
                     ↓
         ┌──────────────────────────┐
         │ Customer clicks Feedback?│
         └────┬─────────────────┬───┘
              │                 │
             YES               NO
              │                 │
              ↓                 ↓
         ┌─────────┐    [No action]
         │ Type    │
         │ message │
         └────┬────┘
              │
              ↓
    Saved to customer_messages table
    status = "unread"
              │
              ↓
    Admin: /view_messages unread
              │
              ↓
    Admin: /view_message <id>
              │
              ↓
    Admin: Click "Send Reply"
              │
              ↓
    Admin types reply
              │
              ↓
    ┌─────────────────────────────┐
    │ Saved + Auto-sent to customer│
    │ status = "replied"           │
    └─────────────────────────────┘
```

---

## Next Steps / Enhancements

Consider adding in the future:
1. **Message Categories** - Tag messages as "complaint", "suggestion", "question", etc.
2. **Message Search** - `/search_messages <keyword>`
3. **Bulk Reply** - Send a standard reply to all unread messages
4. **Export Messages** - Download messages as CSV
5. **Analytics** - Message volume trends over time
6. **Customer Ratings** - Include star ratings with feedback
7. **Message Archival** - Archive old resolved messages
8. **Scheduled Reminders** - Alert you about unanswered messages after X hours

---

## Troubleshooting

### Messages not saving?
- Ensure `customer_messages` table was created (check with `\dt` in psql)
- Check that `/broadcast` command completes successfully

### Can't see feedback button?
- Make sure you're using `/broadcast` or `/pbroadcast` (not other methods)
- Verify customers see the button by checking their screenshot

### Reply not reaching customer?
- Check if customer is still active in the bot (hasn't blocked you)
- Check app logs for send errors
- Customer may need to be in at least one conversation with the bot

---

## Commands Summary

| Command | Usage | Description |
|---------|-------|-------------|
| `/broadcast` | `/broadcast <message>` | Send announcement with feedback button |
| `/view_messages` | `/view_messages [status]` | List customer messages |
| `/view_message` | `/view_message <id>` | View specific message with reply option |
| `/pbroadcast` | `/pbroadcast <template>` | Personalized broadcast (also has feedback button) |

---

## Technical Details

- **Database:** PostgreSQL (customer_messages table)
- **Storage:** Full message text + metadata preserved
- **Notifications:** Automatic to both admin and customer on action
- **Timestamps:** Timezone-aware (uses your configured TZ)
- **Access Control:** Admin-only commands with permission checks

Enjoy managing your customer feedback! 🚀
