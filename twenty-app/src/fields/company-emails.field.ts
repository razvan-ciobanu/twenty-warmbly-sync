import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

import { COMPANY_EMAILS_FIELD_ID } from 'src/constants/universal-identifiers';

export default defineField({
  universalIdentifier: COMPANY_EMAILS_FIELD_ID,
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'emails',
  type: FieldType.EMAILS,
  label: 'Emails',
  description: 'Generic company addresses; the primary one is synced to Warmbly as a contact',
  icon: 'IconMail',
});
