import { defineField, FieldType, STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS } from 'twenty-sdk/define';

export default defineField({
  universalIdentifier: 'c755f8e1-5f15-42b4-a07d-1416a4a52ee6',
  objectUniversalIdentifier: STANDARD_OBJECT_UNIVERSAL_IDENTIFIERS.company.universalIdentifier,
  name: 'emails',
  type: FieldType.EMAILS,
  label: 'Emails',
  description: 'Generic company addresses; the primary one is synced to Warmbly as a contact',
  icon: 'IconMail',
});
