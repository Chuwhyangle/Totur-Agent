import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})

if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = () => {}
}
