"""Local bridge tests with synthetic updates; no real Telegram access."""
import unittest
from unittest.mock import patch
from scripts.local_bot import BotAPI,BotError,check_identity,handle_update,poll_once,worker_call


class FakeBot:
    def __init__(self, updates=None, webhook=''):
        self.updates=updates or [];self.webhook=webhook;self.calls=[]

    def call(self, method, payload=None):
        self.calls.append((method,payload))
        if method=='getMe': return {'is_bot':True,'username':'synthetic_test_bot'}
        if method=='getWebhookInfo': return {'url':self.webhook}
        if method=='getUpdates': return self.updates
        return True


class LocalBotTests(unittest.TestCase):
    def test_webhook_is_never_deleted_to_enable_polling(self):
        bot=FakeBot(webhook='https://example.invalid/telegram/webhook')
        with self.assertRaisesRegex(BotError,'webhook is configured'):
            check_identity(bot,{'bot_username':'synthetic_test_bot'})
        self.assertEqual([m for m,_ in bot.calls],['getMe','getWebhookInfo'])

    def test_wrong_identity_does_not_consume_updates(self):
        bot=FakeBot()
        with self.assertRaisesRegex(BotError,'identity differs'):
            check_identity(bot,{'bot_username':'different_synthetic_bot'})
        self.assertEqual(len(bot.calls),1)

    def test_bridge_uses_worker_reply_and_advances_offset_in_memory(self):
        bot=FakeBot([{'update_id':3},{'update_id':4}])
        reply={'method':'sendMessage','chat_id':777001,'text':'Synthetic response'}
        with patch('scripts.local_bot.worker_call',return_value=reply) as worker:
            offset,retry=poll_once(bot,'http://127.0.0.1:8787','synthetic-secret',0)
        self.assertEqual((offset,retry),(5,False))
        self.assertEqual(worker.call_count,2)
        self.assertEqual(bot.calls[0],('getUpdates',{'offset':0,'timeout':20,'limit':20,'allowed_updates':['message']}))
        self.assertEqual(bot.calls[1],('sendMessage',{'chat_id':777001,'text':'Synthetic response'}))

    def test_retry_keeps_failed_update_unacknowledged(self):
        bot=FakeBot([{'update_id':10},{'update_id':11}])
        with patch('scripts.local_bot.handle_update',side_effect=[None,BotError('Synthetic failure',retryable=True)]):
            self.assertEqual(poll_once(bot,'http://127.0.0.1:8787','synthetic',0),(11,True))

    def test_unsupported_updates_do_not_send_messages(self):
        bot=FakeBot()
        with patch('scripts.local_bot.worker_call',return_value={'ok':True}):
            handle_update({'update_id':1},bot,'http://127.0.0.1:8787','synthetic')
        self.assertEqual(bot.calls,[])

    def test_bridge_preserves_keyboard_and_reply_prompt_options(self):
        for markup in [{'keyboard':[['Synthetic button']],'resize_keyboard':True},{'force_reply':True}]:
            bot=FakeBot();reply={'method':'sendMessage','chat_id':777001,'text':'Synthetic prompt',
                'reply_markup':markup,'link_preview_options':{'is_disabled':True}}
            with patch('scripts.local_bot.worker_call',return_value=reply):
                handle_update({'update_id':1},bot,'http://127.0.0.1:8787','synthetic')
            self.assertEqual(bot.calls[0][1]['reply_markup'],markup)
            self.assertTrue(bot.calls[0][1]['link_preview_options']['is_disabled'])

    def test_arbitrary_bot_methods_and_remote_worker_urls_rejected(self):
        with self.assertRaisesRegex(BotError,'Unsupported'):
            BotAPI('synthetic-unused-token').call('deleteWebhook')
        with self.assertRaisesRegex(BotError,'Only loopback'):
            worker_call('https://example.invalid','/health')
        with patch('scripts.local_bot.worker_call',return_value={'method':'sendDocument','chat_id':777001,'text':'Synthetic'}):
            with self.assertRaisesRegex(BotError,'Unexpected'):
                handle_update({'update_id':1},FakeBot(),'http://127.0.0.1:8787','synthetic')


if __name__=='__main__':unittest.main()
