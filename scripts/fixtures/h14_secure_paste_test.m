/* Native routing test. No Keychain operation, visible window, general
 * pasteboard, capture or real credential. Only a unique private pasteboard
 * containing synthetic owned text. Run only when coordinated by the owner.
 * The field-editor test double redirects paste: to that private pasteboard;
 * this verifies our action/key-equivalent routing, not physical GPUI dispatch. */
#import "../../native/destination-credential.m"

@interface H14PrivatePasteEditor : NSTextView
@property(nonatomic,strong) NSPasteboard *privateBoard;
@property(nonatomic) NSUInteger pasteCalls;
@end
@implementation H14PrivatePasteEditor
- (void)paste:(id)sender {
    (void)sender; _pasteCalls++;
    [self readSelectionFromPasteboard:_privateBoard];
}
@end
@interface H14PasteField : NSSecureTextField
@property(nonatomic,strong) NSText *ownedEditor;
@end
@implementation H14PasteField
- (NSText *)currentEditor {return _ownedEditor;}
@end
static void require(bool pass,const char *check) {
    if(!pass) {fprintf(stderr,"FAIL %s\n",check);exit(1);}
}
int main(void) {
    @autoreleasepool {
        [NSApplication sharedApplication];
        NSApp.mainMenu=[NSMenu new]; // Deliberately no Edit/Paste menu.
        NSPasteboard *board=[NSPasteboard pasteboardWithUniqueName];
        [board declareTypes:@[NSPasteboardTypeString] owner:nil];
        NSString *synthetic=@"MOTIVE_OWNED_SYNTHETIC_PASTE_TEST";
        require([board setString:synthetic forType:NSPasteboardTypeString],"private fixture setup");
        H14PrivatePasteEditor *editor=[[H14PrivatePasteEditor alloc] initWithFrame:NSMakeRect(0,0,400,28)];
        editor.fieldEditor=YES;editor.privateBoard=board;
        MotiveDestinationEnrollment *state=[MotiveDestinationEnrollment new];
        state.phase=MOTIVE_CREDENTIAL_AWAITING_USER;state.alert=[NSAlert new];
        NSView *accessory=destination_secure_accessory(state);
        require([state.field isKindOfClass:NSSecureTextField.class],"production field stays secure");
        H14PasteField *field=[[H14PasteField alloc] initWithFrame:state.field.frame];
        field.ownedEditor=editor;[state.field removeFromSuperview];[accessory addSubview:field];state.field=field;
        state.alert.accessoryView=accessory;[state.alert layout];
        NSButton *button=nil;
        for(NSView *view in accessory.subviews)if([view isKindOfClass:NSButton.class])button=(NSButton *)view;
        require(button && button.target==state && button.action==@selector(pasteCredential:),"local action target");
        require([button.keyEquivalent isEqual:@"v"] && button.keyEquivalentModifierMask==NSEventModifierFlagCommand,"Cmd-V equivalent");
        [button performClick:nil];
        require(editor.pasteCalls==1 && [editor.string isEqual:synthetic],"button routes owned text to editor");
        editor.string=@"";editor.selectedRange=NSMakeRange(0,0);
        NSEvent *event=[NSEvent keyEventWithType:NSEventTypeKeyDown location:NSZeroPoint
            modifierFlags:NSEventModifierFlagCommand timestamp:0 windowNumber:state.alert.window.windowNumber
            context:nil characters:@"v" charactersIgnoringModifiers:@"v" isARepeat:NO keyCode:9];
        require([button performKeyEquivalent:event],"button handles Cmd-V without Edit menu");
        require(editor.pasteCalls==2 && [editor.string isEqual:synthetic],"shortcut routes owned text to editor");
        state.phase=MOTIVE_CREDENTIAL_WRITING;[button performClick:nil];
        require(editor.pasteCalls==2,"no paste after submission");
        state.phase=MOTIVE_CREDENTIAL_AWAITING_USER;state.cancelRequested=YES;[button performClick:nil];
        require(editor.pasteCalls==2,"no paste after cancellation");
        state.cancelRequested=NO;[field removeFromSuperview];[button performClick:nil];
        require(editor.pasteCalls==2,"no paste to detached field");
        editor.string=@"";destination_release_ui(state);[board releaseGlobally];
        puts("PASS secure paste routing: button, Cmd-V, lifecycle guards; private synthetic pasteboard only");
    }
    return 0;
}
