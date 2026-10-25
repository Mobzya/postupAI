import json,shutil,sqlite3,tempfile,unittest
from pathlib import Path
from pipeline.public_backup import create_backup,restore_backup


class PublicBackupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.backup=cls.root/'backup'
        cls.manifest=create_backup(cls.backup)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_actual_database_restores_with_all_stages_and_no_user_data(self):
        result=restore_backup(self.backup,self.root/'restored.sqlite')
        self.assertEqual(result['counts']['academic_rule_versions'],59)
        self.assertEqual(result['counts']['historical_source_observations'],956)
        self.assertEqual(result['counts']['user_profiles'],0)
        db=sqlite3.connect(self.root/'restored.sqlite')
        self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[]);db.close()
        with self.assertRaises(ValueError):restore_backup(self.backup,self.root/'restored.sqlite')

    def test_corruption_is_detected_before_restore(self):
        copy=self.root/'corrupt';shutil.copytree(self.backup,copy)
        with (copy/'public-data.sqlite').open('ab') as f:f.write(b'synthetic_corruption')
        with self.assertRaisesRegex(ValueError,'hash_mismatch'):restore_backup(copy,self.root/'rejected.sqlite')
        self.assertFalse((self.root/'rejected.sqlite').exists())

    def test_manifest_does_not_substitute_integrity_and_counts(self):
        copy=self.root/'wrong-manifest';shutil.copytree(self.backup,copy)
        d=json.loads((copy/'manifest.json').read_text());d['counts']['academic_rule_versions']=999
        (copy/'manifest.json').write_text(json.dumps(d))
        with self.assertRaisesRegex(ValueError,'counts_mismatch'):restore_backup(copy,self.root/'rejected2.sqlite')


if __name__=='__main__':unittest.main()
