# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

from botbuilder.core.turn_context import TurnContext
from .dialog_state import DialogState
from .dialog_turn_status import DialogTurnStatus
from .dialog_turn_result import DialogTurnResult
from .dialog_reason import DialogReason
from .dialog_instance import DialogInstance
from .dialog import Dialog


class DialogContext:
    def __init__(
        self, dialog_set: object, turn_context: TurnContext, state: DialogState
    ):
        if dialog_set is None:
            raise TypeError("DialogContext(): dialog_set cannot be None.")
        # TODO: Circular dependency with dialog_set: Check type.
        if turn_context is None:
            raise TypeError("DialogContext(): turn_context cannot be None.")
        self._turn_context = turn_context
        self._dialogs = dialog_set
        # self._id = dialog_id;
        self._stack = state.dialog_stack
        self.parent = None

    @property
    def dialogs(self):
        """Gets the set of dialogs that can be called from this context.

        :param:
        :return str:
        """
        return self._dialogs

    @property
    def context(self) -> TurnContext:
        """Gets the context for the current turn of conversation.

        :param:
        :return str:
        """
        return self._turn_context

    @property
    def stack(self):
        """Gets the current dialog stack.

        :param:
        :return str:
        """
        return self._stack

    @property
    def active_dialog(self):
        """Return the container link in the database.

        :param:
        :return str:
        """
        if self._stack:
            return self._stack[0]
        return None

    async def begin_dialog(self, dialog_id: str, options: object = None):
        """
        Pushes a new dialog onto the dialog stack.
        :param dialog_id: ID of the dialog to start
        :param options: (Optional) additional argument(s) to pass to the dialog being started.
        """
        if not dialog_id:
            raise TypeError("Dialog(): dialogId cannot be None.")
        # Look up dialog
        dialog = await self.find_dialog(dialog_id)
        if dialog is None:
            raise Exception(
                "'DialogContext.begin_dialog(): A dialog with an id of '%s' wasn't found."
                " The dialog must be included in the current or parent DialogSet."
                " For example, if subclassing a ComponentDialog you can call add_dialog() within your constructor."
                % dialog_id
            )
        # Push new instance onto stack
        instance = DialogInstance()
        instance.id = dialog_id
        instance.state = {}

        self._stack.insert(0, (instance))

        # Call dialog's begin_dialog() method
        return await dialog.begin_dialog(self, options)

    # TODO: Fix options: PromptOptions instead of object
    async def prompt(self, dialog_id: str, options) -> DialogTurnResult:
        """
        Helper function to simplify formatting the options for calling a prompt dialog. This helper will
        take a `PromptOptions` argument and then call.
        :param dialog_id: ID of the prompt to start.
        :param options: Contains a Prompt, potentially a RetryPrompt and if using ChoicePrompt, Choices.
        :return:
        """
        if not dialog_id:
            raise TypeError("DialogContext.prompt(): dialogId cannot be None.")

        if not options:
            raise TypeError("DialogContext.prompt(): options cannot be None.")

        return await self.begin_dialog(dialog_id, options)

    async def continue_dialog(self):
        """
        Continues execution of the active dialog, if there is one, by passing the context object to
        its `Dialog.continue_dialog()` method. You can check `turn_context.responded` after the call completes
        to determine if a dialog was run and a reply was sent to the user.
        :return:
        """
        # Check for a dialog on the stack
        if self.active_dialog is not None:
            # Look up dialog
            dialog = await self.find_dialog(self.active_dialog.id)
            if not dialog:
                raise Exception(
                    "DialogContext.continue_dialog(): Can't continue dialog. A dialog with an id of '%s' wasn't found."
                    % self.active_dialog.id
                )

            # Continue execution of dialog
            return await dialog.continue_dialog(self)

        return DialogTurnResult(DialogTurnStatus.Empty)

    # TODO: instance is DialogInstance
    async def end_dialog(self, result: object = None):
        """
        Ends a dialog by popping it off the stack and returns an optional result to the dialog's
        parent. The parent dialog is the dialog that started the dialog being ended via a call to
        either "begin_dialog" or "prompt".
        The parent dialog will have its `Dialog.resume_dialog()` method invoked with any returned
        result. If the parent dialog hasn't implemented a `resume_dialog()` method then it will be
        automatically ended as well and the result passed to its parent. If there are no more
        parent dialogs on the stack then processing of the turn will end.
        :param result: (Optional) result to pass to the parent dialogs.
        :return:
        """
        await self.end_active_dialog(DialogReason.EndCalled)

        # Resume previous dialog
        if self.active_dialog is not None:
            # Look up dialog
            dialog = await self.find_dialog(self.active_dialog.id)
            if not dialog:
                raise Exception(
                    "DialogContext.EndDialogAsync(): Can't resume previous dialog."
                    " A dialog with an id of '%s' wasn't found." % self.active_dialog.id
                )

            # Return result to previous dialog
            return await dialog.resume_dialog(self, DialogReason.EndCalled, result)

        return DialogTurnResult(DialogTurnStatus.Complete, result)

    async def cancel_all_dialogs(self):
        """
        Deletes any existing dialog stack thus cancelling all dialogs on the stack.
        :param result: (Optional) result to pass to the parent dialogs.
        :return:
        """
        if self.stack:
            while self.stack:
                await self.end_active_dialog(DialogReason.CancelCalled)
            return DialogTurnResult(DialogTurnStatus.Cancelled)

        return DialogTurnResult(DialogTurnStatus.Empty)

    async def find_dialog(self, dialog_id: str) -> Dialog:
        """
        If the dialog cannot be found within the current `DialogSet`, the parent `DialogContext`
        will be searched if there is one.
        :param dialog_id: ID of the dialog to search for.
        :return:
        """
        dialog = await self.dialogs.find(dialog_id)

        if dialog is None and self.parent is not None:
            dialog = await self.parent.find_dialog(dialog_id)
        return dialog

    async def replace_dialog(
        self, dialog_id: str, options: object = None
    ) -> DialogTurnResult:
        """
        Ends the active dialog and starts a new dialog in its place. This is particularly useful
        for creating loops or redirecting to another dialog.
        :param dialog_id: ID of the dialog to search for.
        :param options: (Optional) additional argument(s) to pass to the new dialog.
        :return:
        """
        # End the current dialog and giving the reason.
        await self.end_active_dialog(DialogReason.ReplaceCalled)

        # Start replacement dialog
        return await self.begin_dialog(dialog_id, options)

    async def reprompt_dialog(self):
        """
        Calls reprompt on the currently active dialog, if there is one. Used with Prompts that have a reprompt behavior.
        :return:
        """
        # Check for a dialog on the stack
        if self.active_dialog is not None:
            # Look up dialog
            dialog = await self.find_dialog(self.active_dialog.id)
            if not dialog:
                raise Exception(
                    "DialogSet.reprompt_dialog(): Can't find A dialog with an id of '%s'."
                    % self.active_dialog.id
                )

            # Ask dialog to re-prompt if supported
            await dialog.reprompt_dialog(self.context, self.active_dialog)

    async def end_active_dialog(self, reason: DialogReason):
        instance = self.active_dialog
        if instance is not None:
            # Look up dialog
            dialog = await self.find_dialog(instance.id)
            if dialog is not None:
                # Notify dialog of end
                await dialog.end_dialog(self.context, instance, reason)

            # Pop dialog off stack
            self._stack.pop(0)
