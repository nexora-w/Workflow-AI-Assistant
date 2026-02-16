# Visual Layout Guide

## Main Application Screen

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Workflow AI Assistant                           Welcome, username  [Logout] │
├──────────────────┬─────────────────────────┬────────────────────────────────┤
│                  │                         │                                │
│  Conversations   │     Chat Window         │   Workflow Visualization       │
│  (20% width)     │     (30% width)         │   (50% width)                  │
│                  │                         │                                │
│ ┌──────────────┐ │ ┌─────────────────────┐ │ ┌────────────────────────────┐ │
│ │  [+ New]     │ │ │ Welcome to Workflow │ │ │                            │ │
│ └──────────────┘ │ │ AI Assistant        │ │ │    ╔═══════╗               │ │
│                  │ │                     │ │ │    ║ Start ║               │ │
│ ╭──────────────╮ │ │ Select a           │ │ │    ╚═══╤═══╝               │ │
│ │ New Conver.. │ │ │ conversation or    │ │ │        │                   │ │
│ ╰──────────────╯ │ │ create a new one   │ │ │        ▼                   │ │
│                  │ │                     │ │ │   ┌────────────┐           │ │
│  Customer Flow   │ └─────────────────────┘ │ │   │  Process   │           │ │
│                  │                         │ │   │  Request   │           │ │
│  Onboarding      │                         │ │   └─────┬──────┘           │ │
│                  │                         │ │         │                   │ │
│  Sales Process   │                         │ │         ▼                   │ │
│                  │                         │ │    ╱────────╲              │ │
│                  │                         │ │   ╱ Decision ╲             │ │
│                  │                         │ │   ╲  Point?  ╱             │ │
│                  │                         │ │    ╲────┬───╱              │ │
│                  │                         │ │         │                   │ │
│                  │                         │ │         ▼                   │ │
│                  │                         │ │    ╔═══════╗               │ │
│                  │                         │ │    ║  End  ║               │ │
│                  │                         │ │    ╚═══════╝               │ │
│                  │                         │ │                            │ │
│                  │                         │ │  [Zoom Controls]           │ │
│                  │                         │ │  [Mini Map]                │ │
│                  │                         │ │                            │ │
└──────────────────┴─────────────────────────┴────────────────────────────────┘
```

## Chat Window (Active Conversation)

```
┌───────────────────────────────────────────────┐
│  Chat Window                                  │
├───────────────────────────────────────────────┤
│                                               │
│  User: "Create a customer onboarding process"│
│  10:30 AM                                     │
│                                               │
│                                               │
│  Assistant: "I'll help you design a customer │
│  onboarding workflow. Here's a comprehensive │
│  process:                                     │
│                                               │
│  1. Welcome Email                             │
│  2. Account Setup                             │
│  3. Initial Training                          │
│  4. First Use                                 │
│  5. Follow-up Support                         │
│                                               │
│  The workflow has been visualized on the      │
│  right panel."                                │
│  10:30 AM                                     │
│                                               │
│                                               │
│  User: "Add a quality check step"             │
│  10:31 AM                                     │
│                                               │
│                                               │
│  ●●● (typing indicator)                       │
│                                               │
├───────────────────────────────────────────────┤
│  Describe the workflow you need...            │
│  ┌─────────────────────────────────────────┐ │
│  │                                         │ │
│  │                                         │ │
│  └─────────────────────────────────────────┘ │
│                                    [Send]     │
└───────────────────────────────────────────────┘
```

## Login Screen

```
┌─────────────────────────────────────────┐
│                                         │
│     Workflow AI Assistant               │
│     Sign in to continue                 │
│                                         │
│     ┌─────────────────────────────┐    │
│     │ Username                    │    │
│     │ Enter your username         │    │
│     └─────────────────────────────┘    │
│                                         │
│     ┌─────────────────────────────┐    │
│     │ Password                    │    │
│     │ Enter your password         │    │
│     └─────────────────────────────┘    │
│                                         │
│     ┌─────────────────────────────┐    │
│     │       Sign In               │    │
│     └─────────────────────────────┘    │
│                                         │
│     Don't have an account? Sign up     │
│                                         │
└─────────────────────────────────────────┘
```

## Workflow Node Types

### Start Node (Purple)
```
╔═══════════╗
║   Start   ║
╚═══════════╝
```

### Process Node (Green)
```
┌─────────────┐
│   Process   │
│   Request   │
└─────────────┘
```

### Decision Node (Orange)
```
    ╱──────────╲
   ╱  Decision  ╲
   ╲   Point?   ╱
    ╲──────────╱
```

### End Node (Violet)
```
╔═══════════╗
║    End    ║
╚═══════════╝
```

## Responsive Breakpoints

### Desktop (1920x1080)
- Chat List: 384px (20%)
- Chat Window: 576px (30%)
- Workflow: 960px (50%)

### Laptop (1366x768)
- Chat List: 273px (20%)
- Chat Window: 410px (30%)
- Workflow: 683px (50%)

### Tablet (1024x768)
- Maintains same proportions
- Minimum widths enforced:
  - Chat List: 250px
  - Chat Window: 350px

## Color Scheme

### Primary Colors
- **Primary Purple**: `#667eea` (buttons, accents)
- **Secondary Violet**: `#764ba2` (gradients)
- **Background**: `#f5f5f5` (page background)
- **White**: `#ffffff` (panels, cards)

### Node Colors
- **Start**: `#667eea` (purple)
- **End**: `#764ba2` (violet)
- **Process**: `#48bb78` (green)
- **Decision**: `#f6ad55` (orange)

### Text Colors
- **Primary**: `#333333` (main text)
- **Secondary**: `#666666` (labels)
- **Muted**: `#999999` (placeholders)

### Borders
- **Light**: `#e0e0e0` (dividers)
- **Medium**: `#ddd` (inputs)

## Interactive Elements

### Buttons
- **Primary**: Purple gradient with hover lift
- **Secondary**: Gray with hover darken
- **Danger**: Red tint on hover

### Inputs
- **Default**: Gray border
- **Focus**: Purple border with shadow ring
- **Disabled**: Gray background

### Chat Items
- **Default**: Light gray background
- **Hover**: Darker gray
- **Active**: Purple with white text

## Animations

### Typing Indicator
```
●   ●   ●
  ●   ●
●   ●   ●
```
Bouncing animation with 0.4s delay between dots

### Loading Spinner
```
  ╱─╲
  │ │  (rotating)
  ╲─╱
```
Continuous 360° rotation

### Workflow Transitions
- **Pan**: Smooth drag with momentum
- **Zoom**: Smooth scale with wheel/pinch
- **Node appearance**: Fade in with scale

## Accessibility

### Keyboard Navigation
- Tab: Navigate between elements
- Enter: Submit forms, activate buttons
- Escape: Close dialogs
- Arrow keys: Navigate workflow (when focused)

### Screen Reader Support
- Semantic HTML elements
- ARIA labels where needed
- Alt text for icons
- Clear form labels

## User Experience Flow

1. **First Visit** → Login/Register screen
2. **After Login** → Empty state with "New" button
3. **Create Chat** → Chat added to list and selected
4. **Send Message** → Typing indicator → Response + Workflow
5. **View Workflow** → Interactive diagram with controls
6. **Logout** → Return to login screen

This visual layout ensures an intuitive, productive user experience optimized for workflow design tasks.
