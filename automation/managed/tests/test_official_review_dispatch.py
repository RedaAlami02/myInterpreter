import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import official_review_dispatch as review
import worker

class DispatchTests(unittest.TestCase):
    def test_accepts_both_documented_success_responses(self):
        for status in (200,204):
            api=SimpleNamespace(repo='example/worker',session=Mock())
            api.session.post.return_value.status_code=status
            review.dispatch(api,'main',{'document_sha256':'a'*64})
            self.assertFalse(api.session.post.call_args.kwargs['allow_redirects'])
            self.assertEqual(api.session.post.call_args.kwargs['json']['ref'],'main')

    def test_rejection_never_claims_dispatch(self):
        api=SimpleNamespace(repo='example/worker',session=Mock())
        api.session.post.return_value.status_code=403
        with self.assertRaisesRegex(worker.AcquisitionError,'REVIEW_DISPATCH_FAILED'):
            review.dispatch(api,'main',{})
